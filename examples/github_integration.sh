#!/bin/bash
# Example: GitHub Integration
# This script demonstrates how to use GitHub PR integration

set -e

# Check for GitHub token
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable not set"
    echo ""
    echo "To create a token:"
    echo "1. Go to GitHub Settings → Developer settings → Personal access tokens"
    echo "2. Generate new token (classic)"
    echo "3. Select 'repo' scope"
    echo "4. Export it: export GITHUB_TOKEN='your-token'"
    exit 1
fi

echo "🔗 Generating release notes with GitHub integration..."
echo ""

gitreleasegen generate \
    --unreleased \
    --format markdown \
    --out GITHUB_NOTES.md

echo ""
echo "✅ Release notes with PR information generated!"
echo "📄 Saved to: GITHUB_NOTES.md"
echo ""
echo "Features included:"
echo "  • Pull request titles and numbers"
echo "  • PR author information"
echo "  • Links to PRs and commits"
echo "  • Compare URL between tags"
