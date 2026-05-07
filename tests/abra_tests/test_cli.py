from unittest.mock import patch

from click.testing import CliRunner

from abra.cli import main
from abra.config import ProjectConfig
from abra.core import BranchWorkspace
from abra.git import GitRepo


class TestMain:
    def test_help(self):
        result = CliRunner().invoke(main, ['--help'])

        assert result.exit_code == 0
        assert 'create' in result.output
        assert 'status' in result.output
        assert 'merge-from' in result.output
        assert 'remove' in result.output
        assert 'cleanup' not in result.output

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

    def test_remove_passes_force_flag(self, tmp_path):
        runner = CliRunner()
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(GitRepo, 'current', return_value=repo),
            patch.object(BranchWorkspace, 'remove') as remove_,
        ):
            result = runner.invoke(main, ['remove', 'demo', '--force'])

        assert result.exit_code == 0
        remove_.assert_called_once_with(force=True)
        assert result.output == 'Removed demo.\n'
