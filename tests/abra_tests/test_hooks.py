from unittest.mock import call, patch

import click
import pytest

from abra.config import ProjectConfig
from abra.git import GitRepo
from abra.hooks import HookRunner
from abra.utils import sub_run


class TestHookRunner:
    def test_allows_missing_hook_tasks(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        hooks = HookRunner(
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )

        with patch.object(HookRunner, 'task_file_path', return_value=None):
            hooks.hook_tasks_clean_ensure()

    def test_rejects_dirty_hook_task(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        hooks = HookRunner(
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )
        task_fpath = repo_root / 'tasks' / 'abra-post-create.py'

        with (
            patch.object(HookRunner, 'task_file_path', return_value=task_fpath),
            patch.object(GitRepo, 'path_dirty', return_value=True),
            pytest.raises(click.ClickException, match='abra-post-create'),
        ):
            hooks.hook_task_clean_ensure('post-create')

    def test_rejects_dirty_hook_task_in_external_repo(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        external_repo_root = tmp_path / 'external-repo'
        external_repo_root.mkdir()
        sub_run('git', 'init', external_repo_root, capture=True)
        hooks = HookRunner(
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )
        task_fpath = external_repo_root / 'tasks' / 'abra-post-create.py'
        task_fpath.parent.mkdir()
        task_fpath.write_text('print("hook")\n')

        with (
            patch.object(HookRunner, 'task_file_path', return_value=task_fpath),
            pytest.raises(click.ClickException, match='abra-post-create'),
        ):
            hooks.hook_task_clean_ensure('post-create')

    def test_rejects_non_repo_hook_task_without_git_status_check(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        hooks = HookRunner(
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )
        task_fpath = tmp_path / 'external-script.py'
        task_fpath.write_text('print("hook")\n')

        with (
            patch.object(HookRunner, 'task_file_path', return_value=task_fpath),
            patch.object(GitRepo, 'path_dirty') as path_dirty,
            pytest.raises(click.ClickException, match='abra-post-create'),
        ):
            hooks.hook_task_clean_ensure('post-create')

        path_dirty.assert_not_called()

    def test_all_hook_tasks_clean_check_iterates_configured_hooks(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        hooks = HookRunner(
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )

        with patch.object(HookRunner, 'hook_task_clean_ensure') as hook_task_clean_ensure:
            hooks.hook_tasks_clean_ensure()

        assert hook_task_clean_ensure.call_args_list == [call('post-create'), call('pre-remove')]
