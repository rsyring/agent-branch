# Spec for Abra mods and cleanup

Stndardize on "abra" as identifier:

- Branch should be `abra/<ident>` instead of `agent/<ident>`
- Hook scripts prefix is "abra-" instead of "agent-branch"
- Hook env variables prefix "ABRA_" instead of "AGENT_BRANCH_"

## Cleanup -> remove

Change the cleanup command to `remove`, change the hook name accordingly.

Get rid of the `--branch` option and always remove the branch.

But, put a guard in place, before any change is made, to ensure there are:

- no uncommitted changes in the repo
- no committed changes that have not yet been merged back into the origin branch

Add a `--force` option that will skip the guards and remove everything anyway.

## Repo creation location

Ensure that the repo lcoation is created as a sibling, not child, of the source repo. The
previous readme has some commentary that said it was created inside the source repo. I
want to make sure that isn't happening.

## Examples

Copy the hook examples from the skills test source repo into an examples folder in this
repo

## Documentation updates

Make sure the readme and any docstrings are brought up to date with these changes.

## Decision notes

- The remove guard should ensure abra branch commits have landed somewhere before removal.
- Accept either of these as sufficient:
  - the abra branch has no commits ahead of its configured upstream branch
  - or the abra branch has no commits ahead of the local branch it was originally created
    from
- This should work for local-only workflows and not require a remote-tracking branch.

# Move state file

- Move the state file into the source repo instead of a sibling to it. And rename it to
  'abra-state.json'.
