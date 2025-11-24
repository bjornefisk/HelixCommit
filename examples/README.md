# HelixCommit Examples

This directory contains practical examples demonstrating various use cases of HelixCommit.

## Examples Overview

### 1. Basic Usage (`basic_usage.py`)

The simplest use case - generate release notes for unreleased changes.

```bash
python examples/basic_usage.py
```

**What it does:**
- Generates changelog for commits since the last tag
- Outputs to `RELEASE_NOTES.md`
- Uses default Markdown formatting

### 2. AI Summarization (`ai_summarization.py`)

Use free AI models to enhance your release notes.

```bash
export OPENROUTER_API_KEY="your-key"
python examples/ai_summarization.py
```

**What it does:**
- Uses OpenRouter's free Llama model
- Generates professional summaries of changes
- Caches results to reduce API calls
- Outputs to `AI_RELEASE_NOTES.md`

### 3. Programmatic Usage (`programmatic_usage.py`)

Use HelixCommit as a Python library in your own scripts.

```bash
python examples/programmatic_usage.py
```

**What it does:**
- Demonstrates the Python API
- Shows how to customize changelog generation
- Generates notes between the last two tags

### 4. GitHub Integration (`github_integration.sh`)

Fetch pull request information for richer changelogs.

```bash
export GITHUB_TOKEN="your-token"
./examples/github_integration.sh
```

**What it does:**
- Fetches PR titles, authors, and labels
- Links commits to their pull requests
- Includes PR metadata in output

### 5. Multiple Formats (`multiple_formats.sh`)

Generate release notes in all supported formats.

```bash
./examples/multiple_formats.sh
```

**What it does:**
- Generates Markdown, HTML, and plain text versions
- Demonstrates format-specific features
- Useful for different distribution channels

### 6. CI/CD Integration (`cicd_integration.yml`)

Example GitHub Actions workflow for automated release notes.

```yaml
# See examples/cicd_integration.yml
```

**What it does:**
- Automatically generates notes on new releases
- Publishes to GitHub Releases
- Configurable for different workflows

## Running the Examples

### Prerequisites

1. **Install GitReleaseGen:**
   ```bash
   pip install gitreleasegen
   ```

2. **Have a Git repository with commits:**
   ```bash
   cd your-repo
   git log --oneline  # Should show some commits
   ```

3. **For AI examples, get an API key:**
   - OpenRouter: https://openrouter.ai (free tier available)
   - OpenAI: https://platform.openai.com

4. **For GitHub examples, create a token:**
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Create a token with `repo` scope

### Try Them Out

```bash
# Clone and navigate to examples
cd gitreleasegen/examples

# Make scripts executable
chmod +x *.sh

# Run any example
python basic_usage.py
./github_integration.sh
```

## Customization

All examples can be customized by modifying:
- **Tag ranges**: Change `--since-tag` and `--until-tag`
- **Output format**: Use `--format markdown|html|text`
- **LLM models**: Specify `--openai-model` or `--openrouter-model`
- **Filtering**: Add `--no-merge-commits`, `--max-items`, etc.

## Advanced Examples

### Custom Date Ranges

```bash
gitreleasegen generate \
  --since "$(git log -1 --before='1 month ago' --format='%H')" \
  --until HEAD
```

### Specific File Paths

While not directly supported, you can filter commits before passing to GitReleaseGen:

```bash
# Get commits that touched specific files
git log --format="%H" -- src/api/ | head -n 1
```

### Integration with Release Scripts

```bash
#!/bin/bash
# release.sh - Automated release workflow

VERSION="$1"

# Generate release notes
helixcommit generate \
  --unreleased \
  --use-llm \
  --format markdown \
  --out "releases/v${VERSION}.md"

# Create git tag
git tag -a "v${VERSION}" -F "releases/v${VERSION}.md"

# Push tag
git push origin "v${VERSION}"
```

## Troubleshooting

### No commits found

- **Cause**: No commits in the specified range
- **Fix**: Check your tags with `git tag -l` and commit history with `git log`

### API rate limits

- **Cause**: Too many API calls to OpenAI/OpenRouter
- **Fix**: Use `--summary-cache` to cache results between runs

### GitHub API errors

- **Cause**: Invalid token or rate limit exceeded
- **Fix**: Check token permissions and wait for rate limit reset

### Permission denied on scripts

- **Cause**: Scripts aren't executable
- **Fix**: Run `chmod +x examples/*.sh`

## Contributing Examples

Have a useful example? We'd love to include it! Please:

1. Create a new file in `examples/`
2. Add clear comments and documentation
3. Update this README
4. Submit a pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.
