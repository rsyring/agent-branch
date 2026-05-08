# Spec: more flexible hook checks

We have guards in place on the hooks so that we abort if they have uncommitted changes.

But, we can't assume the hooks exist in the repo. Mise allows hooks from other locations
and it's possible a workspace will want to use one of those.

So, when checking the git status, you will need to find the repo that the hook belongs to
and check it there.

You also should account for the fact that a script is not in a git repo. In that case,
treat it the same as being uncommitted but don't run any git commands that throw
exceptions in that case.

## Decision

- Resolve each hook task file to the git repo that contains that file before checking for
  uncommitted changes.
- If the hook task file is not inside any git repo, treat it as dirty and block the
  operation.

## Status

- Implemented in `HookRunner` by resolving the hook task file's repo before running the
  dirty check.

## Validation

- Added coverage for a dirty hook file that lives in a different git repo.
- Added coverage for a hook file outside any git repo and verified we do not call the git
  status check in that case.
- Targeted hook tests passed.
