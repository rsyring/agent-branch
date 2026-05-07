# Spec: refactor library structure

We have src/abra/branch.py which contains all of our logic.

But that code could be split into different domains. Ones that stick out to me are:

- config
- core
- git
- utils?

Maybe there isn't enough config code to have the not just be in core.

Review what's there and propose the refactor you would make to the modules and tests to
organize the code better. Put your refactor plan below in this spec file.

## Refactor plan

### Goals

- Split `src/abra/branch.py` into focused modules with clear responsibilities.
- Keep the CLI interface and user-facing behavior stable.
- Reorganize tests so they mirror the library modules.
- Allow public imports to change; do not keep `abra.branch` as a compatibility shim.

### Proposed library structure

Replace the current monolith with these modules:

- `src/abra/config.py`
  - `DEFAULT_BRANCH_PREFIX`
  - `DEFAULT_WORKTREE_TEMPLATE`
  - `DEFAULT_HOOK_EVENTS`
  - `default_state_path()`
  - `find_repo_root()`
  - `ProjectConfig`
- `src/abra/core.py`
  - `StateEntry`
  - `WorktreeInfo`
  - `BranchWorkspace`
  - state file locking/load/save helpers or a small `StateStore` kept internal to core
  - `slugify_name()`
  - `yes_no()`
- `src/abra/utils.py`
  - `CalledProcessError`
  - `sub_run()`
- `src/abra/git.py`
  - `parse_worktree_list()`
  - `GitRepo` (branch/worktree/git-query operations currently on `BranchManager`)
- `src/abra/hooks.py`
  - `hook_task_name()`
  - `HookRunner` (mise trust/task existence/task execution/dirty hook checks)

### Design notes

- `core.py` should be the main home for the domain model and orchestration logic. In this
  codebase, state, workspace behavior, and simple data objects are tightly related enough
  to live together without creating a new monolith.
- `utils.py` is acceptable here because the current shared helper surface is small and
  likely to accumulate a few more low-level helpers over time.
- Replace the current all-in-one `BranchManager` with smaller collaborators where that
  improves clarity, but do not force every concern into its own top-level module. The main
  split should be `core`, `git`, `hooks`, `config`, and `utils`.
- Keep `BranchWorkspace` as the main orchestration object because it matches the CLI
  commands and current behavior well.
- Update `src/abra/cli.py` to import from the new modules directly.
- Delete `src/abra/branch.py` once imports have been migrated.

### Proposed test structure

Split `tests/abra_tests/test_branch.py` into:

- `tests/abra_tests/test_config.py`
- `tests/abra_tests/test_core.py`
- `tests/abra_tests/test_git.py`
- `tests/abra_tests/test_hooks.py`
- `tests/abra_tests/test_cli.py` (keep, updating imports as needed)

Test movement should follow responsibility boundaries:

- config defaults/path tests move to `test_config.py`
- slot/state persistence tests move to `test_core.py`
- branch/worktree git behavior tests move to `test_git.py`
- hook environment and hook cleanliness tests move to `test_hooks.py` or `test_core.py`
  depending on where behavior lands
- create/remove/merge/status workflow tests move to `test_core.py`

### Implementation sequence

1. Create the new modules and move code without changing behavior.
2. Refactor `BranchWorkspace` and related state logic into `core.py`, extracting `GitRepo`
   and `HookRunner` as the main supporting collaborators.
3. Update `cli.py` to import the new entry points.
4. Reorganize tests to mirror the new module layout and fix imports.
5. Remove `src/abra/branch.py`.
6. Run targeted tests, then the full relevant test suite.

### Acceptance criteria

- `src/abra/branch.py` no longer exists.
- CLI commands and output remain stable.
- Tests are reorganized to mirror the module layout.
- Existing test coverage still passes after import updates and file moves.
- The new module boundaries are explicit enough that future work on git, hooks, state, or
  workspace orchestration can happen without reopening a monolithic file.
