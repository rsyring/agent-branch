"""CLI entrypoint for the abra command."""

import click
from rich.console import Console
from rich.table import Table

from abra.branch import BranchManager, BranchWorkspace


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
    Manage isolated git worktrees for branch-based agent or app workflows.

    It creates or reuses an `agent/<ident>` branch, creates or reuses a sibling worktree at
    `<repo-parent>/<repo-name>.<ident>`, and allocates a reusable numeric slot stored in a state
    file next to the repo.

    If the worktree defines `agent-branch-post-create` or `agent-branch-pre-cleanup` as mise
    tasks, this CLI will run them inside the worktree. Those hooks receive `AGENT_BRANCH_IDENT`,
    `AGENT_BRANCH_BRANCH`, and `AGENT_BRANCH_SLOT`.

    This tool intentionally stays app-agnostic. Hook tasks can translate the slot into
    app-specific ports, containers, databases, or other local resources.

    Use `create IDENT` to prepare a worktree and allocate a slot. If the worktree defines a mise
    task named `agent-branch-post-create`, it will run inside the worktree with the
    `AGENT_BRANCH_*` environment variables listed above.

    Use `cleanup IDENT` to run the optional `agent-branch-pre-cleanup` hook, remove the worktree,
    and release the slot so it can be reused later.
    """


@main.command()
@click.argument('ident')
def create(ident: str) -> None:
    """
    Create or reuse the branch worktree for IDENT.

    IDENT becomes the branch suffix and worktree suffix. For example, `create demo` uses the
    branch `agent/demo` and the worktree `<repo-parent>/<repo-name>.demo`.
    """

    workspace = BranchWorkspace(ident, manager=BranchManager.current())
    slot = workspace.create()
    click.echo(f'Branch {workspace.ident} is ready at {workspace.worktree_path} (slot {slot}).')


@main.command()
def status() -> None:
    """Show all active branch worktrees recorded in the state file."""

    manager = BranchManager.current()
    click.echo(f'State file: {manager.state_path}')
    entries = manager.state_load()
    if not entries:
        click.echo('No active branch worktrees found.')
        return

    print_status([BranchWorkspace(entry.ident, manager=manager).status_row() for entry in entries])


@main.command()
@click.argument('ident')
def merge_from(ident: str) -> None:
    """
    Fast-forward merge agent/IDENT into the current non-agent branch.

    Run this from the branch you want to update from the agent branch.
    """

    workspace = BranchWorkspace(ident, manager=BranchManager.current())
    target_branch = workspace.merge_from()
    click.echo(f'Merged {workspace.branch_name} into {target_branch}.')


@main.command()
@click.argument('ident')
@click.option(
    '--branch',
    'delete_branch',
    is_flag=True,
    default=False,
    help='Delete the git branch too.',
)
def cleanup(ident: str, delete_branch: bool) -> None:
    """
    Clean up the worktree for IDENT and release its slot.

    Use `--branch` to delete the git branch as part of cleanup.
    """

    BranchWorkspace(ident, manager=BranchManager.current()).cleanup(delete_branch=delete_branch)
    click.echo(f'Cleaned up {ident}.')
