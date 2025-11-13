#!/bin/bash
# Example: Multiple Output Formats
# Generate release notes in all supported formats

set -e

echo "📝 Generating release notes in multiple formats..."
echo ""

# Markdown
echo "1. Generating Markdown..."
gitreleasegen generate \
    --unreleased \
    --format markdown \
    --out notes.md

# HTML
echo "2. Generating HTML..."
gitreleasegen generate \
    --unreleased \
    --format html \
    --out notes.html

# Plain Text
echo "3. Generating plain text..."
gitreleasegen generate \
    --unreleased \
    --format text \
    --out notes.txt

echo ""
echo "✅ Release notes generated in all formats!"
echo ""
echo "Files created:"
echo "  • notes.md   - Markdown (for GitHub, GitLab, etc.)"
echo "  • notes.html - HTML (for websites, emails)"
echo "  • notes.txt  - Plain text (for terminals, logs)"
echo ""
echo "Preview HTML:"
echo "  open notes.html  # macOS"
echo "  xdg-open notes.html  # Linux"
echo "  start notes.html  # Windows"
