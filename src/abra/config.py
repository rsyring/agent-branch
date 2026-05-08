from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

import click


DEFAULT_BRANCH_PREFIX = 'abra/'
DEFAULT_WORKTREE_TEMPLATE = '{project_base}.{ident}'
DEFAULT_HOOK_EVENTS = ('post-create', 'pre-teardown')


def default_state_path(repo_root: Path) -> Path:
    return (repo_root / 'abra-state.json').resolve()


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / '.git').exists():
            return candidate

    raise click.ClickException(f'Could not find a git repository from {current} upward.')


@dataclass(frozen=True)
class ProjectConfig:
    project_base: str
    state_path: Path
    worktree_root: Path
    worktree_template: str = DEFAULT_WORKTREE_TEMPLATE
    branch_prefix: str = DEFAULT_BRANCH_PREFIX
    hook_events: tuple[str, ...] = DEFAULT_HOOK_EVENTS

    @classmethod
    def defaults(cls, repo_root: Path) -> Self:
        project_base = repo_root.name
        return cls(
            project_base=project_base,
            state_path=default_state_path(repo_root),
            worktree_root=repo_root.parent.resolve(),
        )

    def worktree_path(self, ident: str) -> Path:
        name = self.worktree_template.format(project_base=self.project_base, ident=ident)
        return self.worktree_root / name
