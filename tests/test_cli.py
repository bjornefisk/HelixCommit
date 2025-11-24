from pathlib import Path

import git
from typer.testing import CliRunner

from helixcommit.cli import app

runner = CliRunner()


def create_commit(
    repo: git.Repo, base_path: Path, relative: str, content: str, message: str
) -> git.Commit:
    file_path = base_path / relative
    file_path.write_text(content, encoding="utf-8")
    repo.index.add([relative])
    actor = git.Actor("Test User", "test@example.com")
    return repo.index.commit(message, author=actor, committer=actor)


def test_cli_generate_text_output(tmp_path):
    repo = git.Repo.init(tmp_path)
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    second = create_commit(repo, tmp_path, "feature.txt", "Feature", "feat: add feature")

    result = runner.invoke(
        app,
        [
            "--repo",
            str(tmp_path),
            "--since",
            initial.hexsha,
            "--until",
            second.hexsha,
            "--format",
            "text",
            "--no-prs",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Release" in result.output
    assert "add feature" in result.output
