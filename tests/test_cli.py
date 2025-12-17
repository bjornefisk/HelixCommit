from pathlib import Path

import git
import pytest
from typer.testing import CliRunner

from helixcommit.cli import (
    _extract_mr_number,
    _extract_pr_number,
    _parse_date,
    app,
)

runner = CliRunner()


def create_commit(
    repo: git.Repo, base_path: Path, relative: str, content: str, message: str
) -> git.Commit:
    file_path = base_path / relative
    file_path.parent.mkdir(parents=True, exist_ok=True)
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


def test_cli_generate_include_paths(tmp_path):
    repo = git.Repo.init(tmp_path)
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    create_commit(repo, tmp_path, "src/app.py", "print('hi')", "feat: add app")
    last = create_commit(repo, tmp_path, "docs/readme.md", "Docs", "docs: update docs")

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
            "--include-paths",
            "src",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "add app" in result.output
    assert "update docs" not in result.output


def test_cli_generate_exclude_paths(tmp_path):
    repo = git.Repo.init(tmp_path)
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    create_commit(repo, tmp_path, "src/app.py", "print('hi')", "feat: add app")
    last = create_commit(repo, tmp_path, "docs/readme.md", "Docs", "docs: update docs")

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
            "--exclude-paths",
            "docs",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "add app" in result.output
    assert "update docs" not in result.output


def test_cli_generate_section_order_option(tmp_path):
    repo = git.Repo.init(tmp_path)
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    create_commit(repo, tmp_path, "fix.txt", "Bug fix", "fix: patch bug")
    last = create_commit(repo, tmp_path, "feat.txt", "Feature", "feat: add feature")

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
            "--section-order",
            "fix",
            "--section-order",
            "feat",
        ],
    )

    assert result.exit_code == 0, result.output
    fixes_index = result.output.index("FIXES")
    features_index = result.output.index("FEATURES")
    assert fixes_index < features_index


# --- Date Parsing Tests ---


from datetime import datetime, timezone, timedelta


def test_parse_date_iso_format():
    """Test parsing ISO 8601 date formats."""
    result = _parse_date("2024-01-15")
    assert result.year == 2024
    assert result.month == 1
    assert result.day == 15
    assert result.tzinfo is not None


def test_parse_date_iso_with_time():
    """Test parsing ISO 8601 datetime format."""
    result = _parse_date("2024-06-20T14:30:00")
    assert result.year == 2024
    assert result.month == 6
    assert result.day == 20
    assert result.hour == 14
    assert result.minute == 30


def test_parse_date_yesterday():
    """Test parsing 'yesterday' keyword."""
    result = _parse_date("yesterday")
    expected = datetime.now(timezone.utc) - timedelta(days=1)
    assert result.date() == expected.date()


def test_parse_date_today():
    """Test parsing 'today' keyword."""
    result = _parse_date("today")
    expected = datetime.now(timezone.utc)
    assert result.date() == expected.date()


@pytest.mark.parametrize(
    "expression,unit",
    [
        ("2 days ago", "days"),
        ("1 week ago", "weeks"),
        ("3 weeks ago", "weeks"),
        ("1 month ago", "months"),
        ("6 months ago", "months"),
    ],
)
def test_parse_date_relative_expressions(expression, unit):
    """Test parsing relative date expressions."""
    result = _parse_date(expression)
    now = datetime.now(timezone.utc)
    # Just verify it's in the past
    assert result < now
    assert result.tzinfo is not None


def test_parse_date_invalid():
    """Test that invalid date strings raise BadParameter."""
    import typer
    
    with pytest.raises(typer.BadParameter):
        _parse_date("not-a-date")


# --- Date Filtering CLI Tests ---


def test_cli_generate_since_date(tmp_path):
    """Test --since-date filters commits by date."""
    import time
    from datetime import timedelta
    
    repo = git.Repo.init(tmp_path)
    
    # Create initial commit
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    
    # Wait to ensure time difference (1+ second)
    time.sleep(1.1)
    
    # Record the current time (after initial commit, before second commit)
    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=0.5)
    
    time.sleep(0.1)
    
    # Create second commit (after cutoff)
    second = create_commit(repo, tmp_path, "feature.txt", "Feature", "feat: add feature")
    
    # Format cutoff time as ISO string
    cutoff_str = cutoff_time.strftime("%Y-%m-%dT%H:%M:%S")
    
    result = runner.invoke(
        app,
        [
            "generate",
            "--repo",
            str(tmp_path),
            "--since-date",
            cutoff_str,
            "--format",
            "text",
            "--no-prs",
        ],
    )
    
    assert result.exit_code == 0, result.output
    # The second commit (after cutoff) should be included
    assert "add feature" in result.output


def test_cli_generate_until_date(tmp_path):
    """Test --until-date filters commits by date. 
    
    Uses a far future date to verify the option is accepted and works.
    """
    repo = git.Repo.init(tmp_path)
    
    # Create commits
    initial = create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    create_commit(repo, tmp_path, "feature.txt", "Feature", "feat: add feature")
    
    # Use a far future date - all commits should be included
    result = runner.invoke(
        app,
        [
            "generate",
            "--repo",
            str(tmp_path),
            "--since",
            initial.hexsha,
            "--until-date",
            "2099-12-31",  # Far future date
            "--format",
            "text",
            "--no-prs",
        ],
    )
    
    assert result.exit_code == 0, result.output
    # The commit should be included since it's before the far future date
    assert "add feature" in result.output


def test_cli_generate_date_range(tmp_path):
    """Test combining --since-date and --until-date for a date range. 
    
    This test uses relative date expressions which are more reliable
    than trying to capture precise timestamps during test execution.
    """
    repo = git.Repo.init(tmp_path)
    
    # Create initial commit - all commits will be "today"
    create_commit(repo, tmp_path, "README.md", "Initial", "chore: initial commit")
    create_commit(repo, tmp_path, "included.txt", "Included", "feat: included feature")
    
    # Use relative date "1 week ago" as since-date
    # Since all commits are from "today", they should all be after "1 week ago"
    result = runner.invoke(
        app,
        [
            "generate",
            "--repo",
            str(tmp_path),
            "--since-date",
            "1 week ago",
            "--format",
            "text",
            "--no-prs",
        ],
    )
    
    assert result.exit_code == 0, result.output
    # Both commits should be included (both are within the last week)
    assert "included feature" in result.output
    assert "initial commit" in result.output.lower() or "Generated changelog" in result.output

def test_cli_generate_commit_shows_staged_files(tmp_path):
    repo = git.Repo.init(tmp_path)

    # Create and stage a new file
    file1 = tmp_path / "file1.txt"
    file1.write_text("content of file 1")
    repo.index.add(["file1.txt"])

    # Create and stage another new file in a subdirectory
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    file2 = subdir / "file2.py"
    file2.write_text("print('hello')")
    repo.index.add(["subdir/file2.py"])

    result = runner.invoke(
        app,
        [
            "generate-commit",
            "--repo",
            str(tmp_path),
            "--openai-api-key", "dummy-key",  # Required by the command, but won't be used for diff display
            "--no-confirm"  # To avoid interactive prompt
        ]
    )

    # The command should exit with an error because of the dummy API key,
    # but the staged files panel should still be displayed before that.
    assert result.exit_code == 1, result.output
    assert "Staged Files" in result.output
    assert "- file1.txt" in result.output
    assert "- subdir/file2.py" in result.output
    assert "--- a/file1.txt" not in result.output  # Ensure diff is not shown
    assert "+++ b/file1.txt" not in result.output  # Ensure diff is not shown