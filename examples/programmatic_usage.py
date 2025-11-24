#!/usr/bin/env python3
"""
Programmatic API usage example.

This example demonstrates how to use HelixCommit as a Python library
instead of via the command line.
"""

from datetime import datetime
from pathlib import Path

from helixcommit.changelog import ChangelogBuilder
from helixcommit.formatters.markdown import render_markdown
from helixcommit.git_client import CommitRange, GitRepository
from helixcommit.grouper import DEFAULT_ORDER


def generate_release_notes(repo_path: Path, since_tag: str, until_tag: str) -> str:
    """
    Generate release notes programmatically.

    Args:
        repo_path: Path to the Git repository
        since_tag: Starting tag
        until_tag: Ending tag

    Returns:
        Markdown-formatted release notes
    """
    # Initialize Git repository
    git_repo = GitRepository(repo_path)

    # Define commit range
    commit_range = CommitRange(
        since=since_tag,
        until=until_tag,
        include_merges=False,
    )

    # Fetch commits
    commits = list(git_repo.iter_commits(commit_range))
    print(f"Found {len(commits)} commits")

    # Build changelog
    builder = ChangelogBuilder(
        summarizer=None,  # No AI summarization
        section_order=DEFAULT_ORDER,
        include_scopes=True,
        dedupe_prs=False,  # No GitHub integration
    )

    changelog = builder.build(
        version=until_tag,
        release_date=datetime.now(),
        commits=commits,
    )

    # Render to markdown
    return render_markdown(changelog)


def main():
    """Main example function."""
    repo_path = Path.cwd()

    # Get latest two tags
    git_repo = GitRepository(repo_path)
    tags = git_repo.list_tags()

    if len(tags) < 2:
        print("Error: Need at least 2 tags in the repository")
        return

    since_tag = tags[1].name
    until_tag = tags[0].name

    print(f"Generating release notes: {since_tag} → {until_tag}")

    # Generate notes
    markdown = generate_release_notes(repo_path, since_tag, until_tag)

    # Save to file
    output_file = Path("PROGRAMMATIC_NOTES.md")
    output_file.write_text(markdown, encoding="utf-8")

    print(f"\n✅ Release notes saved to: {output_file}")
    print("\nPreview:")
    print("=" * 60)
    print(markdown)


if __name__ == "__main__":
    main()
