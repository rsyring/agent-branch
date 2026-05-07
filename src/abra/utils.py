from __future__ import annotations

from collections.abc import Iterable
from os import environ
import subprocess


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
