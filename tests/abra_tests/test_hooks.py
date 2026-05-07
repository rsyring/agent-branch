from unittest.mock import call, patch

import click
import pytest

from abra.config import ProjectConfig
from abra.git import GitRepo
from abra.hooks import HookRunner


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

    def test_all_hook_tasks_clean_check_iterates_configured_hooks(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        hooks = HookRunner(
            repo=GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root)),
        )

        with patch.object(HookRunner, 'hook_task_clean_ensure') as hook_task_clean_ensure:
            hooks.hook_tasks_clean_ensure()

        assert hook_task_clean_ensure.call_args_list == [call('post-create'), call('pre-remove')]
