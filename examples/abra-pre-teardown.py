#!/usr/bin/env -S uv run --script
"""
Example pre-teardown hook that:

- Runs `docker compose down --remove-orphans --volumes`

"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

import click


@dataclass(frozen=True)
class PreTeardownConfig:
    worktree_dpath: Path

    @classmethod
    def current(cls) -> PreTeardownConfig:
        return cls(worktree_dpath=Path.cwd().resolve())

    def sub_run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=self.worktree_dpath, check=True, text=True)

    def run(self) -> None:
        self.sub_run('docker', 'compose', 'down', '--remove-orphans', '--volumes')


@click.command()
def main() -> None:
    """Example hook to tear down compose resources before teardown."""

    PreTeardownConfig.current().run()


if __name__ == '__main__':
    main()
