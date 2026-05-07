from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click

from abra.git import GitRepo
from abra.utils import sub_run


def hook_task_name(event: str) -> str:
    if event == 'post-create':
        return 'abra-post-create'
    if event == 'pre-remove':
        return 'abra-pre-remove'
    return f'abra-on-{event}'


@dataclass(frozen=True)
class HookRunner:
    repo: GitRepo

    def trust_worktree(self, worktree_path: Path) -> None:
        sub_run('mise', 'trust', worktree_path, capture=True)

    def task_exists(self, task_name: str, *, cwd: Path) -> bool:
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

    def task_file_path(self, task_name: str, *, cwd: Path) -> Path | None:
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

    def task_run(self, task_name: str, *, cwd: Path, env: dict[str, str] | None = None) -> None:
        sub_run('mise', 'run', task_name, cwd=cwd, env=env)

    def hook_task_clean_ensure(self, event: str) -> None:
        task_name = hook_task_name(event)
        if not (task_fpath := self.task_file_path(task_name, cwd=self.repo.repo_root)):
            return
        if not self.repo.path_dirty(task_fpath):
            return

        try:
            display_path = task_fpath.relative_to(self.repo.repo_root)
        except ValueError:
            display_path = task_fpath

        raise click.ClickException(
            f'Commit or stash hook task changes before continuing: {task_name} ({display_path})',
        )

    def hook_tasks_clean_ensure(self) -> None:
        for event in self.repo.config.hook_events:
            self.hook_task_clean_ensure(event)
