"""Example post-create hook.

This example:

- creates a `mise.local.toml` to customize environment variables for Postgres and Django's
  runserver
- runs `uv sync`
- runs `docker compose up ...`
- waits for Postgres to be ready
- runs a custom task in the repo to initialize the database

`hacky` was the app name in the source project this example was copied from. Change those
references to match your app or project.

The script expects these environment variables, which `abra` sets:

- `ABRA_IDENT`
- `ABRA_BRANCH`
- `ABRA_SLOT`
"""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path
import re
import subprocess
import time
from typing import Self

import click


POSTGRES_PORT_START = 17005
# Needed because Django's `runserver` doesn't natively read its port from an environment variable,
# so the app's `manage` entry point translates that value into a CLI option.
RUNSERVER_PORT_START = 17010
CONTAINER_PREFIX = 'hacky-ab'
MISE_LOCAL_TOML_FNAME = 'mise.local.toml'
POSTGRES_READY_ATTEMPTS = 30


def slugify(value: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '-', value).strip('-').lower()
    assert slug
    return slug


@dataclass(frozen=True)
class SetupConfig:
    ident: str
    branch: str
    slot: int
    worktree_dpath: Path

    @classmethod
    def from_environ(cls, env: dict[str, str], *, cwd: Path | None = None) -> Self:
        ident = slugify(env.get('ABRA_IDENT', '').strip())
        if not ident:
            raise click.ClickException('ABRA_IDENT is required.')

        branch = env.get('ABRA_BRANCH', '').strip()
        if not branch:
            raise click.ClickException('ABRA_BRANCH is required.')

        slot_raw = env.get('ABRA_SLOT', '').strip()
        if not slot_raw:
            raise click.ClickException('ABRA_SLOT is required.')

        try:
            slot = int(slot_raw)
        except ValueError as exc:
            raise click.ClickException('ABRA_SLOT must be an integer.') from exc

        return cls(
            ident=ident,
            branch=branch,
            slot=slot,
            worktree_dpath=(cwd or Path.cwd()).resolve(),
        )

    @property
    def postgres_port(self) -> int:
        return POSTGRES_PORT_START + self.slot - 1

    @property
    def runserver_port(self) -> int:
        return RUNSERVER_PORT_START + self.slot - 1

    @property
    def container_name(self) -> str:
        return f'{CONTAINER_PREFIX}-{self.slot}-db'

    def task_env(self) -> dict[str, str]:
        return {
            'DC_POSTGRES_PORT': str(self.postgres_port),
            'DC_CONTAINER_NAME': self.container_name,
            'HACKY_RUNSERVER_PORT': str(self.runserver_port),
        }

    def sub_run(
        self,
        *args: str,
        capture: bool = False,
        env: dict[str, str] | None = None,
        **kwargs,
    ):
        kwargs.setdefault('cwd', self.worktree_dpath)
        kwargs.setdefault('check', True)
        kwargs.setdefault('text', True)
        if capture:
            kwargs.setdefault('capture_output', True)
        if env:
            kwargs['env'] = {
                key: value for key, value in (environ | env).items() if value is not None
            }
        return subprocess.run(args, **kwargs)

    def postgres_ready_wait(self) -> None:
        for _ in range(POSTGRES_READY_ATTEMPTS):
            result = self.sub_run(
                'docker',
                'compose',
                'exec',
                '-T',
                'db',
                'pg_isready',
                '-U',
                'postgres',
                capture=True,
                env=self.task_env(),
                check=False,
            )
            if result.returncode == 0:
                return
            time.sleep(1)

        raise click.ClickException('Postgres did not become ready.')


@click.command()
def main() -> None:
    """Example worktree setup hook."""

    config = SetupConfig.from_environ(environ)
    config.sub_run('mise', 'exec', '--', 'uv', 'sync', env=config.task_env())
    config.sub_run('docker', 'compose', 'up', 'db', '-d', env=config.task_env())
    config.postgres_ready_wait()
    config.sub_run('mise', 'run', 'db-init', env=config.task_env())


if __name__ == '__main__':
    main()
