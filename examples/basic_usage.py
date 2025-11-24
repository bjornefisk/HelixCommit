#!/usr/bin/env python3
"""
Basic usage example for HelixCommit.

This script demonstrates the most common use case: generating release notes
for unreleased changes in the current repository.
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Generate release notes for unreleased changes."""

    # Ensure we're in a git repository
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("Error: Not in a Git repository", file=sys.stderr)
        sys.exit(1)

    # Generate release notes
    result = subprocess.run(
        [
            "helixcommit",
            "generate",
            "--unreleased",
            "--format",
            "markdown",
            "--out",
            "RELEASE_NOTES.md",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("✅ Release notes generated successfully!")
        print(f"📄 Saved to: {Path('RELEASE_NOTES.md').absolute()}")
        print("\nPreview:")
        print("=" * 60)
        with open("RELEASE_NOTES.md") as f:
            print(f.read())
    else:
        print("❌ Failed to generate release notes", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
