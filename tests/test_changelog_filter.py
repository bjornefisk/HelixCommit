"""Tests for the filter_commits function in changelog.py."""

from datetime import datetime, timezone
from typing import List, Optional

import pytest

from helixcommit.changelog import filter_commits
from helixcommit.models import CommitInfo


def make_commit(
    sha: str = "abc123",
    subject: str = "test commit",
    body: str = "",
    author_name: str = "Test User",
    author_email: str = "test@example.com",
    files: Optional[List[str]] = None,
) -> CommitInfo:
    """Create a CommitInfo for testing."""
    now = datetime.now(timezone.utc)
    return CommitInfo(
        sha=sha,
        subject=subject,
        body=body,
        author_name=author_name,
        author_email=author_email,
        authored_date=now,
        committed_date=now,
        files=files or [],
    )


class TestFilterCommitsByType:
    """Tests for include_types filtering."""

    def test_include_types_filters_conventional_commits(self):
        commits = [
            make_commit(sha="1", subject="feat: add login"),
            make_commit(sha="2", subject="fix: resolve bug"),
            make_commit(sha="3", subject="docs: update readme"),
            make_commit(sha="4", subject="chore: update deps"),
        ]

        result = filter_commits(commits, include_types=["feat", "fix"])

        assert len(result) == 2
        assert result[0].sha == "1"
        assert result[1].sha == "2"

    def test_include_types_single_type(self):
        commits = [
            make_commit(sha="1", subject="feat: add login"),
            make_commit(sha="2", subject="fix: resolve bug"),
        ]

        result = filter_commits(commits, include_types=["feat"])

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_include_types_empty_list_returns_all(self):
        commits = [
            make_commit(sha="1", subject="feat: add login"),
            make_commit(sha="2", subject="fix: resolve bug"),
        ]

        result = filter_commits(commits, include_types=[])

        # Empty list means no filtering
        assert len(result) == 2

    def test_include_types_none_returns_all(self):
        commits = [
            make_commit(sha="1", subject="feat: add login"),
            make_commit(sha="2", subject="fix: resolve bug"),
        ]

        result = filter_commits(commits, include_types=None)

        assert len(result) == 2

    def test_include_types_uses_heuristic_for_non_conventional(self):
        commits = [
            make_commit(sha="1", subject="Add new feature for users"),
            make_commit(sha="2", subject="Fixed bug in login"),
        ]

        # "feat" should match heuristic for "Add new feature"
        result = filter_commits(commits, include_types=["feat"])

        assert len(result) == 1
        assert result[0].sha == "1"


class TestFilterCommitsByScope:
    """Tests for exclude_scopes filtering."""

    def test_exclude_scopes_removes_matching(self):
        commits = [
            make_commit(sha="1", subject="feat(auth): add login"),
            make_commit(sha="2", subject="feat(deps): update packages"),
            make_commit(sha="3", subject="fix(ui): fix button"),
        ]

        result = filter_commits(commits, exclude_scopes=["deps"])

        assert len(result) == 2
        assert result[0].sha == "1"
        assert result[1].sha == "3"

    def test_exclude_scopes_multiple(self):
        commits = [
            make_commit(sha="1", subject="feat(auth): add login"),
            make_commit(sha="2", subject="feat(deps): update packages"),
            make_commit(sha="3", subject="fix(ci): fix pipeline"),
        ]

        result = filter_commits(commits, exclude_scopes=["deps", "ci"])

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_exclude_scopes_keeps_no_scope_commits(self):
        commits = [
            make_commit(sha="1", subject="feat: add login"),
            make_commit(sha="2", subject="feat(deps): update packages"),
        ]

        result = filter_commits(commits, exclude_scopes=["deps"])

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_exclude_scopes_empty_list_returns_all(self):
        commits = [
            make_commit(sha="1", subject="feat(deps): update packages"),
        ]

        result = filter_commits(commits, exclude_scopes=[])

        assert len(result) == 1

    def test_exclude_scopes_none_returns_all(self):
        commits = [
            make_commit(sha="1", subject="feat(deps): update packages"),
        ]

        result = filter_commits(commits, exclude_scopes=None)

        assert len(result) == 1


class TestFilterCommitsByAuthor:
    """Tests for author_filter regex filtering."""

    def test_author_filter_by_name(self):
        commits = [
            make_commit(sha="1", author_name="Alice", author_email="alice@example.com"),
            make_commit(sha="2", author_name="Bob", author_email="bob@example.com"),
        ]

        result = filter_commits(commits, author_filter="Alice")

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_author_filter_by_email(self):
        commits = [
            make_commit(sha="1", author_name="Alice", author_email="alice@company.com"),
            make_commit(sha="2", author_name="Bob", author_email="bob@external.com"),
        ]

        result = filter_commits(commits, author_filter="@company\\.com$")

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_author_filter_regex_pattern(self):
        commits = [
            make_commit(sha="1", author_name="Alice Smith", author_email="alice@example.com"),
            make_commit(sha="2", author_name="Bob Jones", author_email="bob@example.com"),
            make_commit(sha="3", author_name="Charlie Smith", author_email="charlie@example.com"),
        ]

        result = filter_commits(commits, author_filter="Smith$")

        assert len(result) == 2
        assert result[0].sha == "1"
        assert result[1].sha == "3"

    def test_author_filter_case_insensitive(self):
        commits = [
            make_commit(sha="1", author_name="Alice", author_email="alice@example.com"),
            make_commit(sha="2", author_name="Bob", author_email="bob@example.com"),
        ]

        result = filter_commits(commits, author_filter="ALICE")

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_author_filter_none_returns_all(self):
        commits = [
            make_commit(sha="1", author_name="Alice"),
            make_commit(sha="2", author_name="Bob"),
        ]

        result = filter_commits(commits, author_filter=None)

        assert len(result) == 2


class TestCombinedFilters:
    """Tests for multiple filters combined."""

    def test_include_types_and_exclude_scopes(self):
        commits = [
            make_commit(sha="1", subject="feat(auth): add login"),
            make_commit(sha="2", subject="feat(deps): update packages"),
            make_commit(sha="3", subject="fix(auth): fix bug"),
        ]

        result = filter_commits(
            commits,
            include_types=["feat"],
            exclude_scopes=["deps"],
        )

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_all_filters_combined(self):
        commits = [
            make_commit(sha="1", subject="feat(auth): add login", author_name="Alice"),
            make_commit(sha="2", subject="feat(auth): add oauth", author_name="Bob"),
            make_commit(sha="3", subject="fix(auth): fix bug", author_name="Alice"),
            make_commit(sha="4", subject="feat(deps): update", author_name="Alice"),
        ]

        result = filter_commits(
            commits,
            include_types=["feat"],
            exclude_scopes=["deps"],
            author_filter="Alice",
        )

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_empty_result_when_no_matches(self):
        commits = [
            make_commit(sha="1", subject="feat: add login", author_name="Alice"),
        ]

        result = filter_commits(
            commits,
            include_types=["fix"],
            author_filter="Bob",
        )

        assert len(result) == 0

    def test_empty_commits_returns_empty(self):
        result = filter_commits(
            [],
            include_types=["feat"],
            exclude_scopes=["deps"],
            author_filter="Alice",
        )

        assert len(result) == 0


class TestFilterCommitsByPath:
    """Tests for include/exclude path filtering."""

    def test_include_paths_requires_match(self):
        commits = [
            make_commit(sha="1", files=["src/app.py"]),
            make_commit(sha="2", files=["docs/readme.md"]),
        ]

        result = filter_commits(commits, include_paths=["src"])

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_include_paths_glob(self):
        commits = [
            make_commit(sha="1", files=["src/app.py"]),
            make_commit(sha="2", files=["docs/readme.md"]),
        ]

        result = filter_commits(commits, include_paths=["docs/*.md"])

        assert len(result) == 1
        assert result[0].sha == "2"

    def test_exclude_paths_filters_commits(self):
        commits = [
            make_commit(sha="1", files=["src/app.py"]),
            make_commit(sha="2", files=["chore/update-deps.txt"]),
        ]

        result = filter_commits(commits, exclude_paths=["chore"])

        assert len(result) == 1
        assert result[0].sha == "1"

    def test_path_filters_ignore_commits_without_files(self):
        commits = [make_commit(sha="1", files=[])]

        result = filter_commits(commits, include_paths=["src"])

        assert result == []

