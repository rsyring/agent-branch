from unittest.mock import patch

import click
import pytest

from abra.config import ProjectConfig
from abra.core import BranchWorkspace, StateEntry, StateStore
from abra.git import GitRepo


class TestStateStore:
    def test_reuses_existing_slot_for_ident(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        state = StateStore(ProjectConfig.defaults(repo_root).state_path)

        first = state.slot_allocate('alpha', source_branch='main')
        second = state.slot_allocate('alpha', source_branch='other-branch')

        assert first == 1
        assert second == 1
        assert state.load() == [StateEntry(ident='alpha', slot=1, source_branch='main')]

    def test_backfills_source_branch_for_existing_slot(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        state = StateStore(ProjectConfig.defaults(repo_root).state_path)

        state.slot_allocate('alpha')
        state.slot_allocate('alpha', source_branch='main')

        assert state.load() == [StateEntry(ident='alpha', slot=1, source_branch='main')]

    def test_reuses_lowest_available_slot(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        state = StateStore(ProjectConfig.defaults(repo_root).state_path)

        assert state.slot_allocate('alpha') == 1
        assert state.slot_allocate('bravo') == 2
        state.slot_release('alpha')

        assert state.slot_allocate('charlie') == 1


class TestBranchWorkspaceHooks:
    def test_hook_env_is_minimal_and_app_agnostic(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        workspace = BranchWorkspace(
            'demo',
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )

        assert workspace.hook_env(slot=3) == {
            'ABRA_IDENT': 'demo',
            'ABRA_BRANCH': 'abra/demo',
            'ABRA_SLOT': '3',
        }

    def test_remove_releases_slot(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        state = StateStore(repo.config.state_path)
        workspace = BranchWorkspace('demo', repo=repo, state=state)
        state.slot_allocate('demo', source_branch='main')

        with (
            patch.object(BranchWorkspace, 'hook_run', return_value=False),
            patch.object(GitRepo, 'worktree_registered', return_value=False),
            patch.object(BranchWorkspace, 'branch_exists', return_value=False),
        ):
            workspace.remove(force=True)

        assert state.load() == []

    def test_pre_remove_runs_before_worktree_cleanup(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        workspace = BranchWorkspace('demo', repo=repo)
        calls: list[str] = []

        def hook_run(event: str, *, slot=None):
            calls.append(f'hook:{event}:{slot}')
            return False

        def worktree_registered(_path):
            calls.append('registered')
            return False

        with (
            patch.object(BranchWorkspace, 'hook_run', side_effect=hook_run),
            patch.object(BranchWorkspace, 'slot', return_value=7),
            patch.object(GitRepo, 'worktree_registered', side_effect=worktree_registered),
            patch.object(StateStore, 'slot_release') as slot_release,
            patch.object(BranchWorkspace, 'branch_exists', return_value=False),
        ):
            workspace.remove(force=True)

        assert calls == ['hook:pre-remove:7', 'registered']
        slot_release.assert_called_once_with('demo')

    def test_remove_refuses_dirty_pre_remove_hook(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        workspace = BranchWorkspace(
            'demo',
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )

        with (
            patch.object(
                workspace.hooks.__class__,
                'hook_task_clean_ensure',
                side_effect=click.ClickException('dirty pre-remove hook'),
            ) as hook_task_clean_ensure,
            patch.object(BranchWorkspace, 'hook_run') as hook_run,
            pytest.raises(click.ClickException, match='dirty pre-remove hook'),
        ):
            workspace.remove()

        hook_task_clean_ensure.assert_called_once_with('pre-remove')
        hook_run.assert_not_called()

    def test_force_skips_remove_safety_checks(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        workspace = BranchWorkspace(
            'demo',
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )

        with (
            patch.object(BranchWorkspace, 'remove_safe_ensure') as remove_safe_ensure,
            patch.object(BranchWorkspace, 'hook_run', return_value=False),
            patch.object(GitRepo, 'worktree_registered', return_value=False),
            patch.object(BranchWorkspace, 'branch_exists', return_value=False),
        ):
            workspace.remove(force=True)

        remove_safe_ensure.assert_not_called()


class TestBranchWorkspaceRemoveGuards:
    def test_allows_remove_when_commits_landed_in_recorded_source_branch(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        state = StateStore(repo.config.state_path)
        workspace = BranchWorkspace('demo', repo=repo, state=state)
        state.slot_allocate('demo', source_branch='feature/demo')

        with (
            patch.object(workspace.hooks.__class__, 'hook_task_clean_ensure'),
            patch.object(BranchWorkspace, 'branch_exists', return_value=True),
            patch.object(GitRepo, 'branch_upstream_name', return_value=None),
            patch.object(GitRepo, 'branch_merged_into', return_value=True) as branch_merged_into,
        ):
            workspace.remove_safe_ensure()

        branch_merged_into.assert_called_once_with('abra/demo', 'feature/demo')

    def test_rejects_remove_when_commits_have_not_landed_anywhere(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        state = StateStore(repo.config.state_path)
        workspace = BranchWorkspace('demo', repo=repo, state=state)
        state.slot_allocate('demo', source_branch='feature/demo')

        with (
            patch.object(workspace.hooks.__class__, 'hook_task_clean_ensure'),
            patch.object(BranchWorkspace, 'branch_exists', return_value=True),
            patch.object(GitRepo, 'branch_upstream_name', return_value='origin/feature/demo'),
            patch.object(GitRepo, 'branch_merged_into', return_value=False),
            pytest.raises(click.ClickException, match='merge them first or use --force'),
        ):
            workspace.remove_safe_ensure()

    def test_rejects_remove_when_worktree_has_uncommitted_changes(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        workspace = BranchWorkspace('demo', repo=repo)
        workspace.worktree_path.mkdir()

        with (
            patch.object(workspace.hooks.__class__, 'hook_task_clean_ensure'),
            patch.object(GitRepo, 'worktree_clean', return_value=False),
            pytest.raises(click.ClickException, match='Commit or stash changes'),
        ):
            workspace.remove_safe_ensure()


class TestBranchWorkspaceCreate:
    def test_branch_ensure_uses_current_branch_as_start_point(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        workspace = BranchWorkspace('demo', repo=repo)

        with (
            patch.object(
                GitRepo,
                'source_branch_current_ensure',
                return_value='financial-planning-intake',
            ),
            patch.object(GitRepo, 'branch_ensure') as branch_ensure,
        ):
            workspace.branch_ensure()

        branch_ensure.assert_called_once_with('abra/demo', 'financial-planning-intake')

    def test_rebase_uses_abra_branch_upstream(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        workspace = BranchWorkspace('demo', repo=repo)

        with (
            patch.object(GitRepo, 'branch_upstream_name', return_value='financial-planning-intake'),
            patch.object(
                GitRepo,
                'branch_rebase_needed',
                return_value=True,
            ) as branch_rebase_needed,
            patch.object(GitRepo, 'worktree_clean', return_value=True),
            patch.object(GitRepo, 'branch_rebase') as branch_rebase,
        ):
            workspace.branch_rebase_ensure()

        branch_rebase_needed.assert_called_once_with('abra/demo', 'financial-planning-intake')
        branch_rebase.assert_called_once_with(workspace.worktree_path, 'financial-planning-intake')

    def test_create_checks_hook_tasks_and_records_source_branch(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        workspace = BranchWorkspace('demo', repo=repo)

        with (
            patch.object(
                BranchWorkspace,
                'source_branch_name',
                return_value='financial-planning-intake',
            ),
            patch.object(workspace.hooks.__class__, 'hook_tasks_clean_ensure') as hook_check,
            patch.object(GitRepo, 'branch_ensure') as branch_ensure,
            patch.object(BranchWorkspace, 'worktree_ensure') as worktree_ensure,
            patch.object(BranchWorkspace, 'branch_rebase_ensure') as rebase_ensure,
            patch.object(workspace.hooks.__class__, 'trust_worktree') as trust_worktree,
            patch.object(StateStore, 'slot_allocate', return_value=1) as slot_allocate,
            patch.object(BranchWorkspace, 'hook_run', return_value=False),
        ):
            workspace.create()

        hook_check.assert_called_once_with()
        branch_ensure.assert_called_once_with('abra/demo', 'financial-planning-intake')
        worktree_ensure.assert_called_once_with()
        rebase_ensure.assert_called_once_with()
        trust_worktree.assert_called_once_with(workspace.worktree_path)
        slot_allocate.assert_called_once_with('demo', source_branch='financial-planning-intake')


class TestBranchWorkspaceMerge:
    def test_merge_from_rejects_abra_branch(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        workspace = BranchWorkspace('demo', repo=repo)

        with (
            patch.object(GitRepo, 'current_branch_name', return_value='abra/demo'),
            patch.object(GitRepo, 'branch_merge_ff_only') as branch_merge_ff_only,
            pytest.raises(click.ClickException, match='cannot be run from an abra branch'),
        ):
            workspace.merge_from()

        branch_merge_ff_only.assert_not_called()

    def test_merge_from_fast_forwards_abra_branch_into_current_branch(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))
        workspace = BranchWorkspace('demo', repo=repo)

        with (
            patch.object(GitRepo, 'current_branch_name', return_value='feature/demo'),
            patch.object(BranchWorkspace, 'branch_exists', return_value=True),
            patch.object(GitRepo, 'branch_merge_ff_only') as branch_merge_ff_only,
        ):
            target_branch = workspace.merge_from()

        assert target_branch == 'feature/demo'
        branch_merge_ff_only.assert_called_once_with('abra/demo')
