from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import fcntl
import json
from json import JSONDecodeError
from pathlib import Path
import re
import shutil
from typing import TYPE_CHECKING

import click


if TYPE_CHECKING:
    from abra.git import GitRepo
    from abra.hooks import HookRunner


def slugify_name(value: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '-', value).strip('-')
    return slug or 'abra'


def yes_no(value: bool) -> str:
    return 'yes' if value else 'no'


@dataclass(frozen=True)
class StateEntry:
    ident: str
    slot: int
    source_branch: str | None = None


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    branch: str | None = None


@dataclass(frozen=True)
class StateStore:
    state_fpath: Path

    @contextmanager
    def locked_file(self):
        self.state_fpath.parent.mkdir(parents=True, exist_ok=True)
        with self.state_fpath.open('a+', encoding='utf-8') as state_file:
            fcntl.flock(state_file.fileno(), fcntl.LOCK_EX)
            state_file.seek(0)
            try:
                yield state_file
            finally:
                fcntl.flock(state_file.fileno(), fcntl.LOCK_UN)

    def load_locked(self, state_file) -> list[StateEntry]:
        raw = state_file.read().strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except JSONDecodeError as exc:
            raise click.ClickException(f'Invalid JSON in state file: {self.state_fpath}') from exc

        rows = data.get('entries', data) if isinstance(data, dict) else data
        return [StateEntry(**row) for row in rows]

    def save_locked(self, state_file, entries: list[StateEntry]) -> None:
        payload = {
            'entries': [asdict(entry) for entry in sorted(entries, key=lambda item: item.ident)],
        }
        state_file.seek(0)
        state_file.truncate()
        state_file.write(json.dumps(payload, indent=2) + '\n')
        state_file.flush()

    def load(self) -> list[StateEntry]:
        if not self.state_fpath.exists():
            return []

        with self.locked_file() as state_file:
            return self.load_locked(state_file)

    def entry(self, ident: str) -> StateEntry | None:
        with self.locked_file() as state_file:
            for entry in self.load_locked(state_file):
                if entry.ident == ident:
                    return entry
        return None

    def slot_allocate(self, ident: str, *, source_branch: str | None = None) -> int:
        with self.locked_file() as state_file:
            entries = self.load_locked(state_file)
            for idx, entry in enumerate(entries):
                if entry.ident == ident:
                    if entry.source_branch is None and source_branch is not None:
                        entries[idx] = StateEntry(
                            ident=entry.ident,
                            slot=entry.slot,
                            source_branch=source_branch,
                        )
                        self.save_locked(state_file, entries)
                    return entry.slot

            used_slots = {entry.slot for entry in entries}
            slot = 1
            while slot in used_slots:
                slot += 1

            entries.append(StateEntry(ident=ident, slot=slot, source_branch=source_branch))
            self.save_locked(state_file, entries)
            return slot

    def slot_release(self, ident: str) -> None:
        with self.locked_file() as state_file:
            entries = [entry for entry in self.load_locked(state_file) if entry.ident != ident]
            self.save_locked(state_file, entries)


def current_repo():
    from abra.git import GitRepo

    return GitRepo.current()


def hooks_for_repo(repo):
    from abra.hooks import HookRunner

    return HookRunner(repo=repo)


@dataclass
class BranchWorkspace:
    ident: str
    repo: GitRepo = field(default_factory=current_repo)
    state: StateStore | None = None
    hooks: HookRunner | None = None

    def __post_init__(self) -> None:
        if self.ident in {'', '.', '..'} or '/' in self.ident or '\\' in self.ident:
            raise click.ClickException(f'Invalid ident: {self.ident}')

        if self.state is None:
            self.state = StateStore(self.repo.config.state_path)
        if self.hooks is None:
            self.hooks = hooks_for_repo(self.repo)

    @property
    def branch_name(self) -> str:
        return f'{self.repo.config.branch_prefix}{self.ident}'

    @property
    def worktree_path(self) -> Path:
        return self.repo.config.worktree_path(self.ident)

    def state_entry(self) -> StateEntry | None:
        assert self.state is not None
        return self.state.entry(self.ident)

    def slot(self) -> int | None:
        if entry := self.state_entry():
            return entry.slot
        return None

    def source_branch_recorded(self) -> str | None:
        if entry := self.state_entry():
            return entry.source_branch
        return None

    def branch_exists(self) -> bool:
        return self.repo.branch_exists(self.branch_name)

    def branch_worktree_path(self) -> Path | None:
        return self.repo.branch_worktree_path(self.branch_name)

    def source_branch_name(self) -> str:
        return self.repo.source_branch_current_ensure()

    def upstream_branch_name(self) -> str:
        if upstream_branch := self.repo.branch_upstream_name(self.branch_name):
            return upstream_branch
        return self.source_branch_name()

    def branch_ensure(self) -> None:
        self.repo.branch_ensure(self.branch_name, self.source_branch_name())

    def branch_rebase_ensure(self) -> None:
        upstream_branch = self.upstream_branch_name()
        if not self.repo.branch_rebase_needed(self.branch_name, upstream_branch):
            return

        if not self.repo.worktree_clean(self.worktree_path):
            raise click.ClickException(
                f'Branch {self.branch_name} needs a rebase onto {upstream_branch}, '
                f'but worktree {self.worktree_path} has uncommitted changes.',
            )

        self.repo.branch_rebase(self.worktree_path, upstream_branch)

    def worktree_ensure(self) -> None:
        self.repo.worktree_root_ensure()
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

        self.repo.worktree_add(self.worktree_path, self.branch_name)

    def hook_env(self, *, slot: int | None = None) -> dict[str, str]:
        env = {
            'ABRA_IDENT': self.ident,
            'ABRA_BRANCH': self.branch_name,
        }
        if slot is not None:
            env['ABRA_SLOT'] = str(slot)
        return env

    def hook_run(self, event: str, *, slot: int | None = None) -> bool:
        from abra.hooks import hook_task_name

        assert self.hooks is not None
        if event not in self.repo.config.hook_events or not self.worktree_path.exists():
            return False

        self.hooks.trust_worktree(self.worktree_path)
        task_name = hook_task_name(event)
        if not self.hooks.task_exists(task_name, cwd=self.worktree_path):
            return False

        self.hooks.task_run(task_name, cwd=self.worktree_path, env=self.hook_env(slot=slot))
        return True

    def create(self) -> int:
        assert self.hooks is not None
        assert self.state is not None
        source_branch = self.source_branch_name()
        self.hooks.hook_tasks_clean_ensure()
        self.repo.branch_ensure(self.branch_name, source_branch)
        self.worktree_ensure()
        self.branch_rebase_ensure()
        self.hooks.trust_worktree(self.worktree_path)
        slot = self.state.slot_allocate(self.ident, source_branch=source_branch)
        self.hook_run('post-create', slot=slot)
        return slot

    def remove_safe_ensure(self) -> None:
        assert self.hooks is not None
        self.hooks.hook_task_clean_ensure('pre-remove')

        if self.worktree_path.exists() and not self.repo.worktree_clean(self.worktree_path):
            raise click.ClickException(
                f'Commit or stash changes in {self.worktree_path} before '
                f'removing {self.branch_name}.',
            )

        if not self.branch_exists():
            return

        target_refs: list[str] = []
        if upstream_branch := self.repo.branch_upstream_name(self.branch_name):
            target_refs.append(upstream_branch)
        if source_branch := self.source_branch_recorded():
            target_refs.append(source_branch)

        target_refs = list(dict.fromkeys(target_refs))
        if any(
            self.repo.branch_merged_into(self.branch_name, target_ref) for target_ref in target_refs
        ):
            return

        compare_target = ', '.join(target_refs) if target_refs else 'an upstream or source branch'
        raise click.ClickException(
            f'Branch {self.branch_name} has commits that have not landed in {compare_target}; '
            'merge them first or use --force.',
        )

    def remove(self, *, force: bool = False) -> None:
        assert self.state is not None
        if not force:
            self.remove_safe_ensure()

        slot = self.slot()
        self.hook_run('pre-remove', slot=slot)

        worktree_registered = self.repo.worktree_registered(self.worktree_path)
        if worktree_registered and self.worktree_path.exists():
            self.repo.worktree_remove(self.worktree_path, force=force)
        elif self.worktree_path.exists():
            shutil.rmtree(self.worktree_path)

        if worktree_registered:
            self.repo.worktree_prune()

        if self.branch_exists():
            self.repo.branch_delete(self.branch_name, force=force)

        self.state.slot_release(self.ident)

    def merge_from(self) -> str:
        target_branch = self.repo.non_abra_branch_current_ensure()
        if not self.branch_exists():
            raise click.ClickException(f'Branch {self.branch_name} does not exist.')

        self.repo.branch_merge_ff_only(self.branch_name)
        return target_branch

    def status_row(self) -> dict[str, str | int]:
        slot = self.slot()
        return {
            'Ident': self.ident,
            'Slot': '' if slot is None else slot,
            'Worktree Exists': yes_no(self.worktree_path.exists()),
            'Branch Exists': yes_no(self.branch_exists()),
        }
