from abra.config import ProjectConfig


class TestProjectConfig:
    def test_worktree_path_is_a_sibling_of_repo_root(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()

        config = ProjectConfig.defaults(repo_root)

        assert config.worktree_path('demo') == tmp_path / 'repo.demo'

    def test_state_path_is_inside_repo_root(self, tmp_path):
        repo_root = tmp_path / 'repo'
        repo_root.mkdir()

        config = ProjectConfig.defaults(repo_root)

        assert config.state_path == repo_root / 'abra-state.json'
