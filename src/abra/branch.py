from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import fcntl
import json
from json import JSONDecodeError
from os import environ
from pathlib import Path
import re
import shutil
import subprocess

import click


DEFAULT_BRANCH_PREFIX = 'agent/'
DEFAULT_WORKTREE_TEMPLATE = '{project_base}.{ident}'
DEFAULT_HOOK_EVENTS = ('post-create', 'pre-cleanup')


class CalledProcessError(subprocess.CalledProcessError):
    @property
    def stdout(self) -> str:
        return self.output or ''

    def __str__(self) -> str:
        return (
            super().__str__()
            + f'\nSTDOUT: {self.stdout[:100]}'
            + f'\nSTDERR: {(self.stderr or "")[:100]}'
        )


def sub_run(
    *args,
    capture: bool = False,
    returns: Iterable[int] | None = None,
    **kwargs,
) -> subprocess.CompletedProcess:
    kwargs.setdefault('check', not bool(returns))
    capture = kwargs.setdefault('capture_output', capture)
    args = args + kwargs.pop('args', ())
    if env := kwargs.pop('env', None):
        kwargs['env'] = {key: value for key, value in (environ | env).items() if value is not None}
    if capture:
        kwargs.setdefault('text', True)

    try:
        result = subprocess.run(args, **kwargs)
        if returns and result.returncode not in returns:
            raise subprocess.CalledProcessError(
                result.returncode,
                args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result
    except subprocess.CalledProcessError as exc:
        if capture:
            raise CalledProcessError(
                exc.returncode,
                exc.cmd,
                output=exc.output,
                stderr=exc.stderr,
            ) from exc
        raise


def slugify_name(value: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '-', value).strip('-')
    return slug or 'agent'


def default_state_path(repo_root: Path, project_base: str) -> Path:
    project_slug = slugify_name(project_base)
    return (repo_root.parent / f'{project_slug}-agent-branch-state.json').resolve()


def hook_task_name(event: str) -> str:
    if event == 'post-create':
        return 'agent-branch-post-create'
    if event == 'pre-cleanup':
        return 'agent-branch-pre-cleanup'
    return f'agent-branch-on-{event}'


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / '.git').exists():
            return candidate

    raise click.ClickException(f'Could not find a git repository from {current} upward.')


def parse_worktree_list(output: str) -> list[WorktreeInfo]:
    worktrees: list[WorktreeInfo] = []
    path: Path | None = None
    branch: str | None = None

    for line in [*output.splitlines(), '']:
        if not line:
            if path is not None:
                worktrees.append(WorktreeInfo(path=path, branch=branch))
            path = None
            branch = None
            continue

        key, _, value = line.partition(' ')
        if key == 'worktree':
            path = Path(value)
        elif key == 'branch':
            branch = value.removeprefix('refs/heads/')

    return worktrees


def yes_no(value: bool) -> str:
    return 'yes' if value else 'no'


@dataclass(frozen=True)
class ProjectConfig:
    project_base: str
    state_path: Path
    worktree_root: Path
    worktree_template: str = DEFAULT_WORKTREE_TEMPLATE
    branch_prefix: str = DEFAULT_BRANCH_PREFIX
    hook_events: tuple[str, ...] = DEFAULT_HOOK_EVENTS

    @classmethod
    def defaults(cls, repo_root: Path) -> ProjectConfig:
        project_base = repo_root.name
        return cls(
            project_base=project_base,
            state_path=default_state_path(repo_root, project_base),
            worktree_root=repo_root.parent.resolve(),
        )

    def worktree_path(self, ident: str) -> Path:
        name = self.worktree_template.format(project_base=self.project_base, ident=ident)
        return self.worktree_root / name


@dataclass(frozen=True)
class StateEntry:
    ident: str
    slot: int


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    branch: str | None = None


class BranchManager:
    def __init__(self, repo_root: Path, config: ProjectConfig):
        self.repo_root = repo_root.resolve()
        self.config = config
        self.state_path = config.state_path
        self.worktree_root = config.worktree_root

    @classmethod
    def current(cls) -> BranchManager:
        repo_root = find_repo_root()
        return cls(repo_root, ProjectConfig.defaults(repo_root))

    @contextmanager
    def state_locked_file(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open('a+', encoding='utf-8') as state_file:
            fcntl.flock(state_file.fileno(), fcntl.LOCK_EX)
            state_file.seek(0)
            try:
                yield state_file
            finally:
                fcntl.flock(state_file.fileno(), fcntl.LOCK_UN)

    def state_load_locked(self, state_file) -> list[StateEntry]:
        raw = state_file.read().strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except JSONDecodeError as exc:
            raise click.ClickException(f'Invalid JSON in state file: {self.state_path}') from exc

        rows = data.get('entries', data) if isinstance(data, dict) else data
        return [StateEntry(**row) for row in rows]

    def state_save_locked(self, state_file, entries: list[StateEntry]) -> None:
        payload = {
            'entries': [asdict(entry) for entry in sorted(entries, key=lambda item: item.ident)],
        }
        state_file.seek(0)
        state_file.truncate()
        state_file.write(json.dumps(payload, indent=2) + '\n')
        state_file.flush()

    def state_load(self) -> list[StateEntry]:
        if not self.state_path.exists():
            return []

        with self.state_locked_file() as state_file:
            return self.state_load_locked(state_file)

    def state_entry(self, ident: str) -> StateEntry | None:
        with self.state_locked_file() as state_file:
            for entry in self.state_load_locked(state_file):
                if entry.ident == ident:
                    return entry
        return None

    def slot_allocate(self, ident: str) -> int:
        with self.state_locked_file() as state_file:
            entries = self.state_load_locked(state_file)
            for entry in entries:
                if entry.ident == ident:
                    return entry.slot

            used_slots = {entry.slot for entry in entries}
            slot = 1
            while slot in used_slots:
                slot += 1

            entries.append(StateEntry(ident=ident, slot=slot))
            self.state_save_locked(state_file, entries)
            return slot

    def slot_release(self, ident: str) -> None:
        with self.state_locked_file() as state_file:
            entries = [
                entry for entry in self.state_load_locked(state_file) if entry.ident != ident
            ]
            self.state_save_locked(state_file, entries)

    def worktrees(self) -> list[WorktreeInfo]:
        result = sub_run('git', 'worktree', 'list', '--porcelain', cwd=self.repo_root, capture=True)
        return parse_worktree_list(result.stdout)

    def branch_exists(self, branch_name: str) -> bool:
        result = sub_run(
            'git',
            'show-ref',
            '--verify',
            '--quiet',
            f'refs/heads/{branch_name}',
            cwd=self.repo_root,
            returns=(0, 1),
        )
        return result.returncode == 0

    def branch_worktree_path(self, branch_name: str) -> Path | None:
        for worktree in self.worktrees():
            if worktree.branch == branch_name:
                return worktree.path
        return None

    def worktree_registered(self, worktree_path: Path) -> bool:
        return any(worktree.path == worktree_path for worktree in self.worktrees())

    def branch_ensure(self, branch_name: str, start_point: str) -> None:
        if self.branch_exists(branch_name):
            if not self.branch_upstream_name(branch_name):
                self.branch_upstream_set(branch_name, start_point)
            return

        sub_run('git', 'branch', '--track', branch_name, start_point, cwd=self.repo_root)

    def branch_upstream_name(self, branch_name: str) -> str | None:
        result = sub_run(
            'git',
            'rev-parse',
            '--abbrev-ref',
            '--symbolic-full-name',
            f'{branch_name}@{{upstream}}',
            cwd=self.repo_root,
            capture=True,
            returns=(0, 1),
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def branch_upstream_set(self, branch_name: str, start_point: str) -> None:
        sub_run('git', 'branch', '--set-upstream-to', start_point, branch_name, cwd=self.repo_root)

    def branch_delete(self, branch_name: str) -> None:
        sub_run('git', 'branch', '--delete', '--force', branch_name, cwd=self.repo_root)

    def branch_rebase_needed(self, branch_name: str, upstream_branch: str) -> bool:
        result = sub_run(
            'git',
            'merge-base',
            '--is-ancestor',
            upstream_branch,
            branch_name,
            cwd=self.repo_root,
            returns=(0, 1),
        )
        return result.returncode == 1

    def worktree_clean(self, worktree_path: Path) -> bool:
        result = sub_run('git', 'status', '--porcelain', cwd=worktree_path, capture=True)
        return not result.stdout.strip()

    def branch_rebase(self, worktree_path: Path, upstream_branch: str) -> None:
        sub_run('git', 'rebase', upstream_branch, cwd=worktree_path)

    def current_branch_name(self) -> str:
        result = sub_run('git', 'branch', '--show-current', cwd=self.repo_root, capture=True)
        return result.stdout.strip()

    def source_branch_current_ensure(self) -> str:
        current_branch = self.non_agent_branch_current_ensure()
        if current_branch != 'detached HEAD':
            return current_branch
        raise click.ClickException('This command must be run from a branch, not detached HEAD.')

    def non_agent_branch_current_ensure(self) -> str:
        current_branch = self.current_branch_name()
        if DEFAULT_BRANCH_PREFIX not in current_branch:
            return current_branch or 'detached HEAD'

        raise click.ClickException(
            f'This command cannot be run from an agent branch ({current_branch}).',
        )

    def branch_merge_ff_only(self, branch_name: str) -> None:
        sub_run('git', 'merge', '--ff-only', branch_name, cwd=self.repo_root)

    def worktree_add(self, worktree_path: Path, branch_name: str) -> None:
        sub_run('git', 'worktree', 'add', worktree_path, branch_name, cwd=self.repo_root)

    def worktree_remove(self, worktree_path: Path) -> None:
        sub_run('git', 'worktree', 'remove', '--force', worktree_path, cwd=self.repo_root)

    def worktree_prune(self) -> None:
        sub_run('git', 'worktree', 'prune', '--expire', 'now', cwd=self.repo_root)

    def worktree_root_ensure(self) -> None:
        self.worktree_root.mkdir(parents=True, exist_ok=True)

    def trust_worktree(self, worktree_path: Path) -> None:
        sub_run('mise', 'trust', worktree_path, capture=True)

    def task_exists(self, task_name: str, cwd: Path) -> bool:
        result = sub_run(
            'mise',
            'tasks',
            'info',
            task_name,
            cwd=cwd,
            capture=True,
            returns=(0, 1),
        )
        return result.returncode == 0

    def task_file_path(self, task_name: str, cwd: Path) -> Path | None:
        result = sub_run(
            'mise',
            'tasks',
            'info',
            task_name,
            cwd=cwd,
            capture=True,
            returns=(0, 1),
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():
            if line.startswith('File: '):
                return Path(line.removeprefix('File: ').strip()).expanduser().resolve()
        return None

    def path_dirty(self, path: Path) -> bool:
        result = sub_run(
            'git',
            'status',
            '--short',
            '--untracked-files=all',
            '--',
            path,
            cwd=self.repo_root,
            capture=True,
        )
        return bool(result.stdout.strip())

    def hook_task_clean_ensure(self, event: str) -> None:
        task_name = hook_task_name(event)
        if not (task_fpath := self.task_file_path(task_name, cwd=self.repo_root)):
            return
        if not self.path_dirty(task_fpath):
            return

        try:
            display_path = task_fpath.relative_to(self.repo_root)
        except ValueError:
            display_path = task_fpath

        raise click.ClickException(
            f'Commit or stash hook task changes before continuing: {task_name} ({display_path})',
        )

    def hook_tasks_clean_ensure(self) -> None:
        for event in self.config.hook_events:
            self.hook_task_clean_ensure(event)

    def task_run(self, task_name: str, cwd: Path, env: dict[str, str] | None = None) -> None:
        sub_run('mise', 'run', task_name, cwd=cwd, env=env)


@dataclass
class BranchWorkspace:
    ident: str
    manager: BranchManager = field(default_factory=BranchManager.current)

    def __post_init__(self) -> None:
        if self.ident in {'', '.', '..'} or '/' in self.ident or '\\' in self.ident:
            raise click.ClickException(f'Invalid ident: {self.ident}')

    @property
    def branch_name(self) -> str:
        return f'{self.manager.config.branch_prefix}{self.ident}'

    @property
    def worktree_path(self) -> Path:
        return self.manager.config.worktree_path(self.ident)

    def state_entry(self) -> StateEntry | None:
        return self.manager.state_entry(self.ident)

    def slot(self) -> int | None:
        if entry := self.state_entry():
            return entry.slot
        return None

    def branch_exists(self) -> bool:
        return self.manager.branch_exists(self.branch_name)

    def branch_worktree_path(self) -> Path | None:
        return self.manager.branch_worktree_path(self.branch_name)

    def source_branch_name(self) -> str:
        return self.manager.source_branch_current_ensure()

    def upstream_branch_name(self) -> str:
        if upstream_branch := self.manager.branch_upstream_name(self.branch_name):
            return upstream_branch
        return self.source_branch_name()

    def branch_ensure(self) -> None:
        self.manager.branch_ensure(self.branch_name, self.source_branch_name())

    def branch_rebase_ensure(self) -> None:
        upstream_branch = self.upstream_branch_name()
        if not self.manager.branch_rebase_needed(self.branch_name, upstream_branch):
            return

        if not self.manager.worktree_clean(self.worktree_path):
            raise click.ClickException(
                f'Branch {self.branch_name} needs a rebase onto {upstream_branch}, '
                f'but worktree {self.worktree_path} has uncommitted changes.',
            )

        self.manager.branch_rebase(self.worktree_path, upstream_branch)

    def worktree_ensure(self) -> None:
        self.manager.worktree_root_ensure()
        if (branch_path := self.branch_worktree_path()) and branch_path != self.worktree_path:
            raise click.ClickException(
                f'Branch {self.branch_name} is already checked out at {branch_path}.',
            )

        if self.worktree_path.exists():
            if branch_path != self.worktree_path:
                raise click.ClickException(
                    f'Worktree path {self.worktree_path} exists but is not registered '
                    f'for {self.branch_name}.',
                )
            return

        if branch_path == self.worktree_path:
            raise click.ClickException(
                f'Worktree {self.worktree_path} is registered but missing on disk.',
            )

        self.manager.worktree_add(self.worktree_path, self.branch_name)

    def hook_env(self, *, slot: int | None = None) -> dict[str, str]:
        env = {
            'AGENT_BRANCH_IDENT': self.ident,
            'AGENT_BRANCH_BRANCH': self.branch_name,
        }
        if slot is not None:
            env['AGENT_BRANCH_SLOT'] = str(slot)
        return env

    def hook_run(self, event: str, *, slot: int | None = None) -> bool:
        if event not in self.manager.config.hook_events or not self.worktree_path.exists():
            return False

        self.manager.trust_worktree(self.worktree_path)
        task_name = hook_task_name(event)
        if not self.manager.task_exists(task_name, cwd=self.worktree_path):
            return False

        self.manager.task_run(task_name, cwd=self.worktree_path, env=self.hook_env(slot=slot))
        return True

    def create(self) -> int:
        self.manager.hook_tasks_clean_ensure()
        self.branch_ensure()
        self.worktree_ensure()
        self.branch_rebase_ensure()
        self.manager.trust_worktree(self.worktree_path)
        slot = self.manager.slot_allocate(self.ident)
        self.hook_run('post-create', slot=slot)
        return slot

    def cleanup(self, *, delete_branch: bool = False) -> None:
        self.manager.hook_task_clean_ensure('pre-cleanup')
        slot = self.slot()
        self.hook_run('pre-cleanup', slot=slot)

        worktree_registered = self.manager.worktree_registered(self.worktree_path)
        if worktree_registered and self.worktree_path.exists():
            self.manager.worktree_remove(self.worktree_path)
        elif self.worktree_path.exists():
            shutil.rmtree(self.worktree_path)

        if worktree_registered:
            self.manager.worktree_prune()

        if delete_branch and self.branch_exists():
            self.manager.branch_delete(self.branch_name)

        self.manager.slot_release(self.ident)

    def merge_from(self) -> str:
        target_branch = self.manager.non_agent_branch_current_ensure()
        if not self.branch_exists():
            raise click.ClickException(f'Branch {self.branch_name} does not exist.')

        self.manager.branch_merge_ff_only(self.branch_name)
        return target_branch

    def status_row(self) -> dict[str, str | int]:
        slot = self.slot()
        return {
            'Ident': self.ident,
            'Slot': '' if slot is None else slot,
            'Worktree Exists': yes_no(self.worktree_path.exists()),
            'Branch Exists': yes_no(self.branch_exists()),
        }
