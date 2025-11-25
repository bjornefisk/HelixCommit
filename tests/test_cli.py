from pathlib import Path

import git
import pytest
from typer.testing import CliRunner

from helixcommit.cli import (
    _extract_mr_number,
    _extract_pr_number,
    app,
)

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
            "generate",
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


# --- GitHub PR Number Extraction Tests ---


@pytest.mark.parametrize(
    "message,expected",
    [
        ("feat: add feature (#123)", 123),
        ("fix: resolve bug (#42)", 42),
        ("Merge pull request #99 from branch", 99),
        ("Pull request #55 merged", 55),
        ("PR #77 - fix issue", 77),
        ("feat: no pr number here", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_pr_number(message, expected):
    """Test GitHub PR number extraction from various message formats."""
    assert _extract_pr_number(message) == expected


# --- GitLab MR Number Extraction Tests ---


@pytest.mark.parametrize(
    "message,expected",
    [
        ("feat: add feature (!123)", 123),
        ("fix: resolve bug (!42)", 42),
        ("Merge request !99 - feature", 99),
        ("MR !55 merged", 55),
        ("mr !77 - fix issue", 77),
        ("feat: no mr number here", None),
        # PR syntax should NOT match MR pattern
        ("feat: add feature (#123)", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_mr_number(message, expected):
    """Test GitLab MR number extraction from various message formats."""
    assert _extract_mr_number(message) == expected


def test_pr_and_mr_patterns_are_distinct():
    """Ensure PR and MR patterns don't overlap."""
    github_message = "feat: add feature (#123)"
    gitlab_message = "feat: add feature (!123)"

    # GitHub pattern matches # syntax
    assert _extract_pr_number(github_message) == 123
    assert _extract_mr_number(github_message) is None

    # GitLab pattern matches ! syntax
    assert _extract_mr_number(gitlab_message) == 123
    assert _extract_pr_number(gitlab_message) is None
