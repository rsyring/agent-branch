from unittest.mock import patch

from abra.config import ProjectConfig
from abra.git import GitRepo


class TestGitRepoBranches:
    def test_creates_abra_branch_from_start_point(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(GitRepo, 'branch_exists', return_value=False),
            patch('abra.git.sub_run') as sub_run,
        ):
            repo.branch_ensure('abra/demo', 'financial-planning-intake')

        sub_run.assert_called_once_with(
            'git',
            'branch',
            '--track',
            'abra/demo',
            'financial-planning-intake',
            cwd=repo.repo_root,
        )

    def test_sets_missing_abra_branch_upstream(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()
        repo = GitRepo(repo_root=repo_root, config=ProjectConfig.defaults(repo_root))

        with (
            patch.object(GitRepo, 'branch_exists', return_value=True),
            patch.object(GitRepo, 'branch_upstream_name', return_value=None),
            patch.object(GitRepo, 'branch_upstream_set') as branch_upstream_set,
        ):
            repo.branch_ensure('abra/demo', 'financial-planning-intake')

        branch_upstream_set.assert_called_once_with('abra/demo', 'financial-planning-intake')
