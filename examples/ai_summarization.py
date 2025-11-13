#!/usr/bin/env python3
"""
AI-powered summarization example.

This example shows how to use OpenRouter with a free Llama model to generate
AI-enhanced release notes.
"""

import os
import subprocess
import sys


def main():
    """Generate AI-powered release notes."""

    # Check for API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set", file=sys.stderr)
        print("\nTo get a free API key:")
        print("1. Visit https://openrouter.ai")
        print("2. Sign up for a free account")
        print("3. Generate an API key")
        print("4. Export it: export OPENROUTER_API_KEY='your-key'")
        sys.exit(1)

    print("🤖 Generating AI-powered release notes...")
    print("   Model: meta-llama/llama-3.3-8b-instruct:free")
    print("   This may take a moment...\n")

    result = subprocess.run(
        [
            "gitreleasegen",
            "generate",
            "--unreleased",
            "--use-llm",
            "--llm-provider",
            "openrouter",
            "--openrouter-model",
            "meta-llama/llama-3.3-8b-instruct:free",
            "--format",
            "markdown",
            "--out",
            "AI_RELEASE_NOTES.md",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("✅ AI-powered release notes generated!")
        print("📄 Saved to: AI_RELEASE_NOTES.md")
        print("\nNote: Summaries are cached in .gitreleasegen-cache/")
        print("      Delete this directory to regenerate summaries.")
    else:
        print("❌ Failed to generate release notes", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
