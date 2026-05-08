# Agent Branch (abra)

[![nox](https://github.com/rsyring/agent-branch/actions/workflows/nox.yaml/badge.svg)](https://github.com/rsyring/agent-branch/actions/workflows/nox.yaml)

`abra` is a CLI tool for simplifying the management of git worktrees for branch-based
parallel development.

Abra uses "workspace" as the term to encompass the repo, worktree, branches, and other
resources associated with its management activities.

Its main use case is multi-tree agentic development.

## Usage

Note: `<ident>` is the workspace identifier. It should be slug-like, e.g. "a-cool-feature"
or "1573-launch-rocket".

- `abra create <ident> [--base-branch]`
  - Creates or reuses a workspace with the given `<ident>`
  - Uses a sibling worktree named `<base-repo>.<ident>`
  - Uses a git branch at `abra/<ident>`
  - Runs the `post-create` hook inside the workspace repo
- `abra run-hook <ident> <hook-ident> [<hook-ident> ...]`
  - Re-runs one or more hooks in an existing abra workspace
  - Runs them in the order given
  - Useful when doing iterative development on hook scripts
- `abra status`: shows existing workspaces
- `abra merge-from <ident>`
  - Fast-forwards the current branch from `abra/<ident>`
  - Runs only from non-abra branches
  - Intended to be used by the origin repo to pull changes in from a workspace
  - Fast-forward only, on the assumption that workspace branches have been rebased onto
    the origin repo/branch
- `abra teardown <ident> [--force]`
  - Runs the `pre-teardown` hook
  - Deletes the workspace worktree and branch
  - Refuses to tear down uncommitted or unmerged work without `--force`

## Hooks

`abra` uses `mise` tasks as hooks to support customizing workspace configuration, setup,
and teardown.

- `abra-post-create`
  - Runs after create in the workspace repo
  - Likely runs **before** the repo's environment is set up, so this hook script usually
    needs to be self-contained
- `abra-pre-teardown`
  - Runs before teardown in the workspace repo

For hook iteration, `abra run-hook <ident> post-create` reruns the existing hook in-place
without rechecking workspace creation. Multiple hook-ident values can be passed and are
run in order.

When hooks run, `abra` provides these environment variables to the tasks:

- `ABRA_IDENT`: the workspace ident provided to `create`
- `ABRA_BRANCH`: the full git branch, i.e. `abra/<ident>`
- `ABRA_SLOT`: an integer that will be unique among all existing abra workspaces

`abra` intentionally stays app-agnostic. Hook tasks should translate the slot into
app-specific ports, containers, databases, or other local resources to avoid collisions.

Example hook scripts adapted from the skills test source repo are available in
`examples/`.

## Dev

### Copier Template

Project structure and tooling mostly derive from the
[Coppy](https://github.com/level12/coppy), see its documentation for context and
additional instructions.

This project can be updated from the upstream repo, see
[Updating a Project](https://github.com/level12/coppy?tab=readme-ov-file#template-updates).

### Project Setup

From zero to passing tests:

1. Ensure [host dependencies](https://github.com/level12/coppy/wiki/Mise) are installed

2. Start docker service dependencies (if applicable):

   `docker compose up -d`

3. Sync the [project](https://docs.astral.sh/uv/concepts/projects/) virtual environment
   with the lock file:

   `uv sync`

4. Configure prek:

   `prek install`

5. Run tests:

   `nox`

### prek instead of pre-commit

This project uses prek instead of pre-commit.

### Versions

Versions are date-based. A `bump` action exists to help manage versions:

```shell
  # Show current version
  mise bump --show

  # Bump version based on date, tag, and push:
  mise bump

  # See other options
  mise bump -- --help
```
