"""CLI entrypoint for the abra command."""

import click
from rich.console import Console
from rich.table import Table

from abra.config import DEFAULT_HOOK_EVENTS
from abra.core import BranchWorkspace, StateStore
from abra.git import GitRepo


@click.group()
def main() -> None:
    """
    Manage isolated git worktrees for branch-based abra workflows.

    Abra uses `abra/<ident>` branches, sibling worktrees, reusable numeric slots, and
    optional hook tasks while staying app-agnostic.
    """


@main.command()
@click.argument('ident')
@click.option(
    '--base-branch',
    type=str,
    default=None,
    help='Base the new abra branch on this branch instead of the current branch.',
)
def create(ident: str, base_branch: str | None) -> None:
    """
    Create or reuse the branch worktree for IDENT.

    IDENT becomes the branch suffix and worktree suffix. For example, `create demo` uses
    `abra/demo` and `<repo-parent>/<repo-name>.demo`.

    If the worktree defines an `abra-post-create` mise task, abra runs it with
    `ABRA_IDENT`, `ABRA_BRANCH`, and `ABRA_SLOT`.
    """

    workspace = BranchWorkspace(ident, repo=GitRepo.current())
    slot = workspace.create(base_branch=base_branch)
    click.echo(f'Branch {workspace.ident} is ready at {workspace.worktree_path} (slot {slot}).')


@main.command(name='run-hook')
@click.argument('ident')
@click.argument(
    'hook-idents',
    nargs=-1,
    required=True,
    type=click.Choice(DEFAULT_HOOK_EVENTS),
)
def run_hook(ident: str, hook_idents: tuple[str, ...]) -> None:
    """
    Run one or more hook identifiers again for IDENT.

    Hooks run for an existing abra worktree in the order given and reuse the recorded
    `ABRA_IDENT`, `ABRA_BRANCH`, and `ABRA_SLOT` values.

    This is especially useful while iterating on a hook like `post-create`.
    """

    workspace = BranchWorkspace(ident, repo=GitRepo.current())
    slot = 0
    for hook_ident in hook_idents:
        slot = workspace.hook_run_ensure(hook_ident)

    hook_ident_list = ', '.join(hook_idents)
    click.echo(
        f'Ran {hook_ident_list} for {workspace.ident} at {workspace.worktree_path} (slot {slot}).',
    )


@main.command()
def status() -> None:
    """
    Show active branch worktrees for the current repo.

    Displays the state file path and whether each recorded worktree and branch still exists.
    """

    repo = GitRepo.current()
    state = StateStore(repo.config.state_path)
    click.echo(f'State file: {repo.config.state_path}')
    entries = state.load()
    if not entries:
        click.echo('No active branch worktrees found.')
        return

    rows = [BranchWorkspace(entry.ident, repo=repo, state=state).status_row() for entry in entries]

    table = Table()
    for header in rows[0]:
        table.add_column(header)
    for row in rows:
        table.add_row(*(str(value) for value in row.values()))
    Console().print(table)


@main.command()
@click.argument('ident')
def merge_from(ident: str) -> None:
    """
    Fast-forward merge abra/IDENT into the current non-abra branch.

    Run this from the branch you want to update from the abra branch.
    """

    workspace = BranchWorkspace(ident, repo=GitRepo.current())
    target_branch = workspace.merge_from()
    click.echo(f'Merged {workspace.branch_name} into {target_branch}.')


@main.command(name='remove')
@click.argument('ident')
@click.option(
    '--force',
    'force_',
    is_flag=True,
    default=False,
    help='Skip remove safety guards and delete the worktree and branch anyway.',
)
def remove_(ident: str, force_: bool) -> None:
    """
    Remove the worktree for IDENT, delete the branch, and release its slot.

    If the worktree defines `abra-pre-remove`, abra runs it before deleting anything.

    By default this refuses to remove dirty or unmerged work. Use `--force` to override.
    """

    BranchWorkspace(ident, repo=GitRepo.current()).remove(force=force_)
    click.echo(f'Removed {ident}.')
