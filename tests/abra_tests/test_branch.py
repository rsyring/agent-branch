from unittest.mock import call, patch

import click
import pytest

from abra import branch


class TestBranchManagerSlots:
    def test_reuses_existing_slot_for_ident(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )

        first = manager.slot_allocate('alpha')
        second = manager.slot_allocate('alpha')

        assert first == 1
        assert second == 1
        assert manager.state_load() == [branch.StateEntry(ident='alpha', slot=1)]

    def test_reuses_lowest_available_slot(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )

        assert manager.slot_allocate('alpha') == 1
        assert manager.slot_allocate('bravo') == 2
        manager.slot_release('alpha')

        assert manager.slot_allocate('charlie') == 1


class TestBranchManagerBranches:
    def test_creates_agent_branch_from_start_point(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )

        with (
            patch.object(branch.BranchManager, 'branch_exists', return_value=False),
            patch.object(branch, 'sub_run') as sub_run,
        ):
            manager.branch_ensure('agent/demo', 'financial-planning-intake')

        sub_run.assert_called_once_with(
            'git',
            'branch',
            '--track',
            'agent/demo',
            'financial-planning-intake',
            cwd=manager.repo_root,
        )

    def test_sets_missing_agent_branch_upstream(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )

        with (
            patch.object(branch.BranchManager, 'branch_exists', return_value=True),
            patch.object(branch.BranchManager, 'branch_upstream_name', return_value=None),
            patch.object(branch.BranchManager, 'branch_upstream_set') as branch_upstream_set,
        ):
            manager.branch_ensure('agent/demo', 'financial-planning-intake')

        branch_upstream_set.assert_called_once_with('agent/demo', 'financial-planning-intake')


class TestBranchWorkspaceHooks:
    def test_hook_env_is_minimal_and_app_agnostic(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        workspace = branch.BranchWorkspace(
            'demo',
            manager=branch.BranchManager(
                repo_root=repo_root,
                config=branch.ProjectConfig.defaults(repo_root),
            ),
        )

        assert workspace.hook_env(slot=3) == {
            'AGENT_BRANCH_IDENT': 'demo',
            'AGENT_BRANCH_BRANCH': 'agent/demo',
            'AGENT_BRANCH_SLOT': '3',
        }

    def test_cleanup_releases_slot(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)
        manager.slot_allocate('demo')

        with (
            patch.object(branch.BranchWorkspace, 'hook_run', return_value=False),
            patch.object(branch.BranchManager, 'worktree_registered', return_value=False),
        ):
            workspace.cleanup()

        assert manager.state_load() == []

    def test_pre_cleanup_runs_before_worktree_cleanup(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)
        calls: list[str] = []

        def hook_run(event: str, *, slot=None):
            calls.append(f'hook:{event}:{slot}')
            return False

        def worktree_registered(_path):
            calls.append('registered')
            return False

        with (
            patch.object(branch.BranchWorkspace, 'hook_run', side_effect=hook_run),
            patch.object(branch.BranchWorkspace, 'slot', return_value=7),
            patch.object(
                branch.BranchManager,
                'worktree_registered',
                side_effect=worktree_registered,
            ),
            patch.object(branch.BranchManager, 'slot_release') as slot_release,
        ):
            workspace.cleanup()

        assert calls == ['hook:pre-cleanup:7', 'registered']
        slot_release.assert_called_once_with('demo')

    def test_cleanup_refuses_dirty_pre_cleanup_hook(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)

        with (
            patch.object(
                branch.BranchManager,
                'hook_task_clean_ensure',
                side_effect=click.ClickException('dirty pre-cleanup hook'),
            ) as hook_task_clean_ensure,
            patch.object(branch.BranchWorkspace, 'hook_run') as hook_run,
            pytest.raises(click.ClickException, match='dirty pre-cleanup hook'),
        ):
            workspace.cleanup()

        hook_task_clean_ensure.assert_called_once_with('pre-cleanup')
        hook_run.assert_not_called()


class TestBranchManagerHookTasks:
    def test_allows_missing_hook_tasks(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )

        with patch.object(branch.BranchManager, 'task_file_path', return_value=None):
            manager.hook_tasks_clean_ensure()

    def test_rejects_dirty_hook_task(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        task_fpath = repo_root / 'tasks' / 'agent-branch-post-create.py'

        with (
            patch.object(branch.BranchManager, 'task_file_path', return_value=task_fpath),
            patch.object(branch.BranchManager, 'path_dirty', return_value=True),
            pytest.raises(click.ClickException, match='agent-branch-post-create'),
        ):
            manager.hook_task_clean_ensure('post-create')

    def test_all_hook_tasks_clean_check_iterates_configured_hooks(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )

        with patch.object(branch.BranchManager, 'hook_task_clean_ensure') as hook_task_clean_ensure:
            manager.hook_tasks_clean_ensure()

        assert hook_task_clean_ensure.call_args_list == [call('post-create'), call('pre-cleanup')]


class TestBranchWorkspaceCreate:
    def test_branch_ensure_uses_current_branch_as_start_point(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)

        with (
            patch.object(
                branch.BranchManager,
                'source_branch_current_ensure',
                return_value='financial-planning-intake',
            ),
            patch.object(branch.BranchManager, 'branch_ensure') as branch_ensure,
        ):
            workspace.branch_ensure()

        branch_ensure.assert_called_once_with('agent/demo', 'financial-planning-intake')

    def test_rebase_uses_agent_branch_upstream(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)

        with (
            patch.object(
                branch.BranchManager,
                'branch_upstream_name',
                return_value='financial-planning-intake',
            ),
            patch.object(
                branch.BranchManager,
                'branch_rebase_needed',
                return_value=True,
            ) as branch_rebase_needed,
            patch.object(branch.BranchManager, 'worktree_clean', return_value=True),
            patch.object(branch.BranchManager, 'branch_rebase') as branch_rebase,
        ):
            workspace.branch_rebase_ensure()

        branch_rebase_needed.assert_called_once_with('agent/demo', 'financial-planning-intake')
        branch_rebase.assert_called_once_with(workspace.worktree_path, 'financial-planning-intake')

    def test_create_checks_hook_tasks_before_creating_worktree(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)

        with (
            patch.object(branch.BranchManager, 'hook_tasks_clean_ensure') as hook_check,
            patch.object(branch.BranchWorkspace, 'branch_ensure') as branch_ensure,
            patch.object(branch.BranchWorkspace, 'worktree_ensure') as worktree_ensure,
            patch.object(branch.BranchWorkspace, 'branch_rebase_ensure') as rebase_ensure,
            patch.object(branch.BranchManager, 'trust_worktree') as trust_worktree,
            patch.object(branch.BranchManager, 'slot_allocate', return_value=1),
            patch.object(branch.BranchWorkspace, 'hook_run', return_value=False),
        ):
            workspace.create()

        hook_check.assert_called_once_with()
        branch_ensure.assert_called_once_with()
        worktree_ensure.assert_called_once_with()
        rebase_ensure.assert_called_once_with()
        trust_worktree.assert_called_once_with(workspace.worktree_path)


class TestBranchWorkspaceMerge:
    def test_merge_from_rejects_agent_branch(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)

        with (
            patch.object(branch.BranchManager, 'current_branch_name', return_value='agent/demo'),
            patch.object(branch.BranchManager, 'branch_merge_ff_only') as branch_merge_ff_only,
            pytest.raises(click.ClickException, match='cannot be run from an agent branch'),
        ):
            workspace.merge_from()

        branch_merge_ff_only.assert_not_called()

    def test_merge_from_fast_forwards_agent_branch_into_current_branch(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = branch.BranchManager(
            repo_root=repo_root,
            config=branch.ProjectConfig.defaults(repo_root),
        )
        workspace = branch.BranchWorkspace('demo', manager=manager)

        with (
            patch.object(branch.BranchManager, 'current_branch_name', return_value='feature/demo'),
            patch.object(branch.BranchWorkspace, 'branch_exists', return_value=True),
            patch.object(branch.BranchManager, 'branch_merge_ff_only') as branch_merge_ff_only,
        ):
            target_branch = workspace.merge_from()

        assert target_branch == 'feature/demo'
        branch_merge_ff_only.assert_called_once_with('agent/demo')
