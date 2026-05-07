"""CLI entrypoint for the abra command."""

import click
from rich.console import Console
from rich.table import Table

from abra.core import BranchWorkspace, StateStore
from abra.git import GitRepo


def print_status(rows: list[dict[str, str | int]]) -> None:
    table = Table()
    for header in rows[0]:
        table.add_column(header)
    for row in rows:
        table.add_row(*(str(value) for value in row.values()))
    Console().print(table)


@click.group()
def main() -> None:
    """
    Manage isolated git worktrees for branch-based abra workflows.

    It creates or reuses an `abra/<ident>` branch, creates or reuses a sibling worktree at
    `<repo-parent>/<repo-name>.<ident>`, and allocates a reusable numeric slot stored in a state
    file next to the repo.

    If the worktree defines `abra-post-create` or `abra-pre-remove` as mise tasks, this CLI will
    run them inside the worktree. Those hooks receive `ABRA_IDENT`, `ABRA_BRANCH`, and
    `ABRA_SLOT`.

    This tool intentionally stays app-agnostic. Hook tasks can translate the slot into
    app-specific ports, containers, databases, or other local resources.

    Use `create IDENT` to prepare a worktree and allocate a slot. If the worktree defines a mise
    task named `abra-post-create`, it will run inside the worktree with the `ABRA_*`
    environment variables listed above.

    Use `remove IDENT` to run the optional `abra-pre-remove` hook, remove the worktree and branch,
    and release the slot so it can be reused later.
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

    IDENT becomes the branch suffix and worktree suffix. For example, `create demo` uses the
    branch `abra/demo` and the worktree `<repo-parent>/<repo-name>.demo`.
    """

    workspace = BranchWorkspace(ident, repo=GitRepo.current())
    slot = workspace.create(base_branch=base_branch)
    click.echo(f'Branch {workspace.ident} is ready at {workspace.worktree_path} (slot {slot}).')


@main.command()
def status() -> None:
    """Show all active branch worktrees recorded in the state file."""

    repo = GitRepo.current()
    state = StateStore(repo.config.state_path)
    click.echo(f'State file: {repo.config.state_path}')
    entries = state.load()
    if not entries:
        click.echo('No active branch worktrees found.')
        return

    print_status(
        [BranchWorkspace(entry.ident, repo=repo, state=state).status_row() for entry in entries],
    )


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

    By default this refuses to remove dirty or unmerged work. Use `--force` to override.
    """

    BranchWorkspace(ident, repo=GitRepo.current()).remove(force=force_)
    click.echo(f'Removed {ident}.')
