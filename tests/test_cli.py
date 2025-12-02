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


# --- Filtering Tests ---


def test_cli_generate_include_types(tmp_path):
    """Test --include-types filters commits by type."""
    repo = git.Repo.init(tmp_path)
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    create_commit(repo, tmp_path, "feature.txt", "Feature", "feat: add feature")
    create_commit(repo, tmp_path, "bugfix.txt", "Fix", "fix: resolve bug")
    last = create_commit(repo, tmp_path, "docs.txt", "Docs", "docs: update docs")

    result = runner.invoke(
        app,
        [
            "generate",
            "--repo",
            str(tmp_path),
            "--since",
            initial.hexsha,
            "--until",
            last.hexsha,
            "--format",
            "text",
            "--no-prs",
            "--include-types",
            "feat",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "add feature" in result.output
    assert "resolve bug" not in result.output
    assert "update docs" not in result.output


def test_cli_generate_exclude_scopes(tmp_path):
    """Test --exclude-scopes filters out commits with specified scopes."""
    repo = git.Repo.init(tmp_path)
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    create_commit(repo, tmp_path, "feature.txt", "Feature", "feat(auth): add auth")
    create_commit(repo, tmp_path, "deps.txt", "Deps", "chore(deps): update packages")
    last = create_commit(repo, tmp_path, "ui.txt", "UI", "feat(ui): improve button")

    result = runner.invoke(
        app,
        [
            "generate",
            "--repo",
            str(tmp_path),
            "--since",
            initial.hexsha,
            "--until",
            last.hexsha,
            "--format",
            "text",
            "--no-prs",
            "--exclude-scopes",
            "deps",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "add auth" in result.output
    assert "improve button" in result.output
    assert "update packages" not in result.output


def test_cli_generate_author_filter(tmp_path):
    """Test --author-filter filters commits by author regex."""
    repo = git.Repo.init(tmp_path)
    alice = git.Actor("Alice", "alice@company.com")
    bob = git.Actor("Bob", "bob@external.com")

    # Initial commit
    readme = tmp_path / "README.md"
    readme.write_text("Initial", encoding="utf-8")
    repo.index.add(["README.md"])
    initial = repo.index.commit("chore: initial", author=alice, committer=alice)

    # Alice's commit
    alice_file = tmp_path / "alice.txt"
    alice_file.write_text("Alice feature", encoding="utf-8")
    repo.index.add(["alice.txt"])
    repo.index.commit("feat: alice feature", author=alice, committer=alice)

    # Bob's commit
    bob_file = tmp_path / "bob.txt"
    bob_file.write_text("Bob feature", encoding="utf-8")
    repo.index.add(["bob.txt"])
    last = repo.index.commit("feat: bob feature", author=bob, committer=bob)

    result = runner.invoke(
        app,
        [
            "generate",
            "--repo",
            str(tmp_path),
            "--since",
            initial.hexsha,
            "--until",
            last.hexsha,
            "--format",
            "text",
            "--no-prs",
            "--author-filter",
            "@company\\.com$",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "alice feature" in result.output
    assert "bob feature" not in result.output


def test_cli_generate_combined_filters(tmp_path):
    """Test combining multiple filter options."""
    repo = git.Repo.init(tmp_path)
    alice = git.Actor("Alice", "alice@company.com")

    # Initial commit
    readme = tmp_path / "README.md"
    readme.write_text("Initial", encoding="utf-8")
    repo.index.add(["README.md"])
    initial = repo.index.commit("chore: initial", author=alice, committer=alice)

    # feat(auth) - should be included
    auth_file = tmp_path / "auth.txt"
    auth_file.write_text("Auth", encoding="utf-8")
    repo.index.add(["auth.txt"])
    repo.index.commit("feat(auth): add auth", author=alice, committer=alice)

    # feat(deps) - should be excluded
    deps_file = tmp_path / "deps.txt"
    deps_file.write_text("Deps", encoding="utf-8")
    repo.index.add(["deps.txt"])
    repo.index.commit("feat(deps): update deps", author=alice, committer=alice)

    # fix(auth) - should be excluded (not feat)
    fix_file = tmp_path / "fix.txt"
    fix_file.write_text("Fix", encoding="utf-8")
    repo.index.add(["fix.txt"])
    last = repo.index.commit("fix(auth): fix auth bug", author=alice, committer=alice)

    result = runner.invoke(
        app,
        [
            "generate",
            "--repo",
            str(tmp_path),
            "--since",
            initial.hexsha,
            "--until",
            last.hexsha,
            "--format",
            "text",
            "--no-prs",
            "--include-types",
            "feat",
            "--exclude-scopes",
            "deps",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "add auth" in result.output
    assert "update deps" not in result.output
    assert "fix auth bug" not in result.output
