from unittest.mock import call, patch

from click.testing import CliRunner

from abra.cli import main
from abra.config import ProjectConfig
from abra.core import BranchWorkspace
from abra.git import GitRepo


class TestMain:
    def test_help(self):
        result = CliRunner().invoke(main, ['--help'])

        assert result.exit_code == 0
        assert 'A CLI tool to ease management of abra workspaces' in result.output
        assert 'create' in result.output
        assert 'run-hook' in result.output
        assert 'status' in result.output
        assert 'merge-from' in result.output
        assert 'teardown' in result.output
        assert 'Create or reuse the abra workspace for IDENT.' in result.output
        assert 'Run one or more hook identifiers again for IDENT.' in result.output
        assert 'Show active abra workspaces for the current repo.' in result.output
        assert 'Fast-forward merge abra/IDENT into the current non-abra branch.' in result.output
        assert 'teardown    Tear down the abra workspace for IDENT' in result.output
        assert (
            'This is especially useful while iterating on a hook like `post-create`.'
            not in result.output
        )
        assert 'By default this refuses to tear down dirty or unmerged work.' not in result.output
        assert 'cleanup' not in result.output

    def test_create_help_shows_workspace_details(self):
        result = CliRunner().invoke(main, ['create', '--help'])

        assert result.exit_code == 0
        assert 'Create or reuse the abra workspace for IDENT.' in result.output
        assert 'If the workspace defines an `abra-post-create` mise task' in result.output

    def test_run_hook_help_shows_rerun_details(self):
        result = CliRunner().invoke(main, ['run-hook', '--help'])

        assert result.exit_code == 0
        assert 'Run one or more hook identifiers again for IDENT.' in result.output
        assert 'reuse the' in result.output
        assert 'recorded `ABRA_IDENT`, `ABRA_BRANCH`, and `ABRA_SLOT` values.' in result.output
        assert 'existing abra workspace' in result.output
        assert (
            'This is especially useful while iterating on a hook like `post-create`.'
            in result.output
        )

    def test_status_help_shows_state_details(self):
        result = CliRunner().invoke(main, ['status', '--help'])

        assert result.exit_code == 0
        assert 'Show active abra workspaces for the current repo.' in result.output
        assert 'Displays the state file path' in result.output

    def test_teardown_help_shows_teardown_details(self):
        result = CliRunner().invoke(main, ['teardown', '--help'])

        assert result.exit_code == 0
        assert 'Tear down the abra workspace for IDENT' in result.output
        assert 'release its' in result.output
        assert 'If the workspace defines `abra-pre-teardown`' in result.output
        assert 'By default this refuses to tear down dirty or unmerged work.' in result.output

    def test_create_passes_base_branch(self, tmp_path):
        runner = CliRunner()
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(GitRepo, 'current', return_value=repo),
            patch.object(BranchWorkspace, 'create', return_value=2) as create,
        ):
            result = runner.invoke(main, ['create', 'demo', '--base-branch', 'release/1.2'])

        assert result.exit_code == 0
        create.assert_called_once_with(base_branch='release/1.2')
        assert (
            result.output
            == f'Branch demo is ready at {repo.config.worktree_path("demo")} (slot 2).\n'
        )

    def test_run_hook_passes_multiple_events_in_order(self, tmp_path):
        runner = CliRunner()
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(GitRepo, 'current', return_value=repo),
            patch.object(BranchWorkspace, 'hook_run_ensure', return_value=2) as hook_run_ensure,
        ):
            result = runner.invoke(main, ['run-hook', 'demo', 'post-create', 'pre-teardown'])

        assert result.exit_code == 0
        assert hook_run_ensure.call_args_list == [call('post-create'), call('pre-teardown')]
        assert (
            result.output == 'Ran post-create, pre-teardown '
            f'for demo at {repo.config.worktree_path("demo")} (slot 2).\n'
        )

    def test_run_hook_rejects_invalid_hook_ident(self):
        result = CliRunner().invoke(main, ['run-hook', 'demo', 'not-a-hook'])

        assert result.exit_code != 0
        assert "Invalid value for '{post-create|pre-teardown}...'" in result.output

    def test_merge_from_reports_success(self, tmp_path):
        runner = CliRunner()
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(GitRepo, 'current', return_value=repo),
            patch.object(BranchWorkspace, 'merge_from', return_value='feature/demo') as merge_from,
        ):
            result = runner.invoke(main, ['merge-from', 'demo'])

        assert result.exit_code == 0
        merge_from.assert_called_once_with()
        assert result.output == 'Merged abra/demo into feature/demo.\n'

    def test_teardown_passes_force_flag(self, tmp_path):
        runner = CliRunner()
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(GitRepo, 'current', return_value=repo),
            patch.object(BranchWorkspace, 'teardown') as teardown,
        ):
            result = runner.invoke(main, ['teardown', 'demo', '--force'])

        assert result.exit_code == 0
        teardown.assert_called_once_with(force=True)
        assert result.output == 'Tore down demo.\n'
