# Spec: cli to run hook

## Problem statement

When iterating on a hook for a project, the branch and work tree repo are already present.
We need to the ability to re-run the create hook repeatedly while we troubleshoot/build
the hook script that is running.

Does the current `create` command suffice? Is it idempotent? Can we just keep re-running
it?

If not, what do you suggest for cli improvements to help with this scenario?

## Findings

- `create` already reuses the existing branch, worktree, and slot.
- `create` is not a good hook-iteration loop because it also reruns branch/worktree checks
  and refuses dirty hook task files before continuing.

## Decision

- Add `run-hook <ident> <hook-ident> [<hook-ident> ...]` for existing abra worktrees.
- It reruns a configured hook with the same `ABRA_*` environment, including the recorded
  slot.
- `hook-ident` values are validated by the CLI with `click.Choice`.
- When multiple hook-ident values are provided, they run in the order given.
- It intentionally avoids the clean-hook-task guard used by `create`, so local hook edits
  can be tested repeatedly.

## Validation

- `ruff format && ruff check --fix --extend-fixable F401 && ruff format`
- `pytest tests/abra_tests/test_cli.py tests/abra_tests/test_core.py`
- Result: passing
