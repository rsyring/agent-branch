# AgentBranch

[![nox](https://github.com/rsyring/agent-branch/actions/workflows/nox.yaml/badge.svg)](https://github.com/rsyring/agent-branch/actions/workflows/nox.yaml)

`abra` is a CLI tool for simplifying the creation of git worktrees for branch-based
parallel development.

Its main use case is multi-tree agentic development.

## Usage

- `abra create <ident>`
  - Creates a worktree next to the base repo named `<base-repo>.<ident>`
  - Creates a git branch for that worktree at `abra/<ident>`
  - Runs the `post-create` hook inside the new worktree repository
- `abra status`: shows existing abra worktrees
- `abra merge-from <ident>`
  - Fast-forwards the current branch from `abra/<ident>`
  - Runs only from non-abra branches
- `abra remove <ident> [--force]`
  - Does not remove uncommitted or unmerged changes without `--force`
  - Runs the `pre-remove` hook
  - Deletes the worktree repository and branch

## Hooks

`abra` uses `mise` tasks as hooks to support customizing worktree repository
configuration, setup, and teardown.

- `abra-post-create`: runs after create in the worktree repo
- `abra-pre-remove`: runs before remove in the worktree repo

When hooks run, `abra` provides these environment variables to the tasks:

- `ABRA_IDENT`: the `<ident>` provided to `create`
- `ABRA_BRANCH`: the full git branch, i.e. `abra/<ident>`
- `ABRA_SLOT`: an integer that will be unique among all existing abra worktrees

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
