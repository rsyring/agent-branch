# Spec: change remove to teardown

## Scope

Change the `remove` command and related taxonomy to `teardown`.

- Update user-facing command/help text.
- Rename the hook event from `pre-remove` to `pre-teardown`.
- Update related file names and developer-facing docs.

## Progress

- Audited CLI, hook, core, README, example, and test touchpoints for the rename.

## Validation

- Targeted CLI, core, and hook tests pass with the teardown naming.
- Ruff format/check passes after the rename updates.
