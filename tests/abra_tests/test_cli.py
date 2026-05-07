from unittest.mock import patch

from click.testing import CliRunner

from abra.branch import BranchManager, BranchWorkspace, ProjectConfig
from abra.cli import main


class TestMain:
    def test_help(self):
        result = CliRunner().invoke(main, ['--help'])

        assert result.exit_code == 0
        assert 'create' in result.output
        assert 'status' in result.output
        assert 'merge-from' in result.output
        assert 'cleanup' in result.output

    def test_merge_from_reports_success(self, tmp_path):
        runner = CliRunner()
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        manager = BranchManager(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(BranchManager, 'current', return_value=manager),
            patch.object(BranchWorkspace, 'merge_from', return_value='feature/demo') as merge_from,
        ):
            result = runner.invoke(main, ['merge-from', 'demo'])

        assert result.exit_code == 0
        merge_from.assert_called_once_with()
        assert result.output == 'Merged agent/demo into feature/demo.\n'
