from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

import click

from abra.config import DEFAULT_BRANCH_PREFIX, ProjectConfig, find_repo_root
from abra.core import WorktreeInfo
from abra.utils import sub_run


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


@dataclass(frozen=True)
class GitRepo:
    repo_root: Path
    config: ProjectConfig

    @classmethod
    def current(cls) -> Self:
        repo_root = find_repo_root()
        return cls(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

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

    def ref_exists(self, ref_name: str) -> bool:
        result = sub_run(
            'git',
            'rev-parse',
            '--verify',
            '--quiet',
            f'{ref_name}^{{commit}}',
            cwd=self.repo_root,
            returns=(0, 1),
        )
        return result.returncode == 0

    def branch_delete(self, branch_name: str, *, force: bool = False) -> None:
        delete_arg = '--force' if force else '--delete'
        sub_run('git', 'branch', delete_arg, branch_name, cwd=self.repo_root)

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

    def branch_merged_into(self, branch_name: str, target_ref: str) -> bool:
        if not self.ref_exists(branch_name) or not self.ref_exists(target_ref):
            return False

        result = sub_run(
            'git',
            'merge-base',
            '--is-ancestor',
            branch_name,
            target_ref,
            cwd=self.repo_root,
            returns=(0, 1),
        )
        return result.returncode == 0

    def worktree_clean(self, worktree_path: Path) -> bool:
        result = sub_run('git', 'status', '--porcelain', cwd=worktree_path, capture=True)
        return not result.stdout.strip()

    def branch_rebase(self, worktree_path: Path, upstream_branch: str) -> None:
        sub_run('git', 'rebase', upstream_branch, cwd=worktree_path)

    def current_branch_name(self) -> str:
        result = sub_run('git', 'branch', '--show-current', cwd=self.repo_root, capture=True)
        return result.stdout.strip()

    def source_branch_current_ensure(self) -> str:
        current_branch = self.non_abra_branch_current_ensure()
        if current_branch != 'detached HEAD':
            return current_branch
        raise click.ClickException('This command must be run from a branch, not detached HEAD.')

    def non_abra_branch_current_ensure(self) -> str:
        current_branch = self.current_branch_name()
        if DEFAULT_BRANCH_PREFIX not in current_branch:
            return current_branch or 'detached HEAD'

        raise click.ClickException(
            f'This command cannot be run from an abra branch ({current_branch}).',
        )

    def branch_merge_ff_only(self, branch_name: str) -> None:
        sub_run('git', 'merge', '--ff-only', branch_name, cwd=self.repo_root)

    def worktree_add(self, worktree_path: Path, branch_name: str) -> None:
        sub_run('git', 'worktree', 'add', worktree_path, branch_name, cwd=self.repo_root)

    def worktree_remove(self, worktree_path: Path, *, force: bool = False) -> None:
        cmd = ['git', 'worktree', 'remove']
        if force:
            cmd.append('--force')
        cmd.append(worktree_path)
        sub_run(*cmd, cwd=self.repo_root)

    def worktree_prune(self) -> None:
        sub_run('git', 'worktree', 'prune', '--expire', 'now', cwd=self.repo_root)

    def worktree_root_ensure(self) -> None:
        self.config.worktree_root.mkdir(parents=True, exist_ok=True)

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
