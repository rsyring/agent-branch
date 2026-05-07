"""
Example pre-remove hook that:

- Runs `docker compose down --remove-orphans --volumes`

"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

import click


@dataclass(frozen=True)
class PreRemoveConfig:
    worktree_dpath: Path

    @classmethod
    def current(cls) -> PreRemoveConfig:
        return cls(worktree_dpath=Path.cwd().resolve())

    def sub_run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=self.worktree_dpath, check=True, text=True)

    def run(self) -> None:
        self.sub_run('docker', 'compose', 'down', '--remove-orphans', '--volumes')


@click.command()
def main() -> None:
    """Example hook to tear down compose resources before remove."""

    PreRemoveConfig.current().run()


if __name__ == '__main__':
    main()
