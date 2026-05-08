# Spec - command --help

The initial help/docstring for `abra --help` is too detailed. It's putting a bunch of info
in there that is sub-command specific.

Move those details to the sub-command's docstring/help. Ensure each subcommand has:

- Single/concise statement of usage as the first sentance of the docstring.
- Appropriate additional details below for visibility when using `<command> --help`

## Decision

- Keep `abra --help` focused on a concise, command-agnostic description of the tool.
- Move command-specific behavior and examples into the relevant subcommand help text.
- Use each subcommand docstring's first sentence as the concise summary shown in top-level
  help.

## Validation

- `ruff format && ruff check --fix --extend-fixable F401 && ruff format`
- `pytest tests/abra_tests/test_cli.py`
- Result: passing
