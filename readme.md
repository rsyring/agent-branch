# AgentBranch
[![nox](https://github.com/rsyring/agent-branch/actions/workflows/nox.yaml/badge.svg)](https://github.com/rsyring/agent-branch/actions/workflows/nox.yaml)

Agent branch (`abra`) is a cli tool for simplifying the creation of git worktrees for branch based
parallel development.

It's main use case is multi-tree agentic development.

## Usage

- `abra create <ident>`
   - Creates a worktree next to the base repo named `<base-repo>.<ident>`
   - Creates a git branch for that worktree at `agent/<ident>`
   - Runs `post-create` hook inside the new worktree repo
- `abra status`: shows existing abra repos
- `abra merge-from <ident>`
   - Does a fast-forward merge on branch `agent/<ident>`
   - Will only run from non-abra repos
- `abra cleanup demo [--branch]`
   - Delete the worktree and, optionally, the branch

## Hooks

Abra uses `mise` tasks as hooks to support customizing the worktree repo config and setup /
teardown.

- `agent-branch-post-create`: ran after create in the worktree repo
- `agent-branch-pre-cleanup`: ran before cleanup in the worktree repo

When hooks run, `abra` provides these environment variables to the tasks:

- `AGENT_BRANCH_IDENT`: the `<ident>` provided to `create`
- `AGENT_BRANCH_BRANCH`: the full git branch, i.e. `agent/<ident>`
- `AGENT_BRANCH_SLOT`: an integer that will be unique among all existing abra worktrees

`abra` intentionally stays app-agnostic. Hook tasks SHOULD translate the slot into app-specific
ports, containers, databases, or other local resources to avoid collisions.

## Dev


### Copier Template

Project structure and tooling mostly derives from the [Coppy](https://github.com/level12/coppy),
see its documentation for context and additional instructions.

This project can be updated from the upstream repo, see
[Updating a Project](https://github.com/level12/coppy?tab=readme-ov-file#template-updates).


### Project Setup

From zero to hero (passing tests that is):

1. Ensure [host dependencies](https://github.com/level12/coppy/wiki/Mise) are installed

2. Start docker service dependencies (if applicable):

   `docker compose up -d`

3. Sync [project](https://docs.astral.sh/uv/concepts/projects/) virtualenv w/ lock file:

   `uv sync`

4. Configure prek:

   `prek install`

5. Run tests:

   `nox`


### prek instead of pre-commit

This project uses prek instead of pre-commit.


### Versions

Versions are date based.  A `bump` action exists to help manage versions:

```shell

  # Show current version
  mise bump --show

  # Bump version based on date, tag, and push:
  mise bump

  # See other options
  mise bump -- --help
```
