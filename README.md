# HelixCommit

[![CI](https://github.com/bjornefisk/HelixCommit/actions/workflows/ci.yml/badge.svg)](https://github.com/bjornefisk/HelixCommit/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**HelixCommit** turns Git history into polished, publish-ready release notes. It understands Conventional Commits, enriches entries with GitHub pull requests, and can summarize changes with OpenAI-compatible LLMs.

## Features

- **Automated change log** -> Build structured release notes from commits and tags.
- **AI summarization** -> Optional OpenAI/OpenRouter support with caching to minimize costs.
- **AI Commit Generation** -> Generate commit messages from staged changes with a free AI model.
- **Conventional Commits friendly** -> Detects types, scopes, and breaking changes automatically.
- **GitHub enrichment** -> Resolves pull requests and links commits for richer context.
- **Multiple outputs** -> Render Markdown, HTML, or plain text.
- **Fast + resilient** -> Uses GitPython when available with CLI fallback.

## Zero-config Quickstart

```bash
pip install helixcommit

# Generate release notes with no external services
# - works offline
# - skips GitHub API calls
helixcommit generate --unreleased --no-prs --format markdown > RELEASE_NOTES.md

# Or for a specific tag range
helixcommit generate --since-tag v1.2.0 --until-tag v1.2.1 --format html --out dist/release.html

# Generate a commit message from staged changes (uses free AI model)
helixcommit generate-commit
```

### From source (development)

```bash
git clone https://github.com/bjornefisk/helixcommit.git
cd helixcommit
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Smoke test
helixcommit --help
pytest -q
```

### Common options

- `--repo PATH` – Point to a different repository (defaults to the current directory).
- `--since / --until` – Limit the commit range to specific refs or SHAs.
- `--no-prs` – Skip GitHub API lookups.
- `--no-include-scopes` – Hide commit scopes in output.

### Optional environment variables

- `OPENAI_API_KEY` – Required only when using `--use-llm` with the OpenAI provider.
- `OPENROUTER_API_KEY` – Required only when using `--use-llm --llm-provider openrouter`.
- `GITHUB_TOKEN` – Optional; improves GitHub API rate limits when fetching PR data. Not required when using `--no-prs`.

## Community & Support

Join the HelixCommit community on Discord: https://discord.gg/UewHHrxNRE

- Welcome: `#rules`, `#announcements` (release notes), `#roadmap`
- Community: `#general`, `#showcase`, `#introductions`
- Support: `#help-installation`, `#help-usage`, `#help-errors`, `#faq` (read-only)
- Development: `#dev-general`, `#issues`, `#pull-requests`, `#architecture`, `#ai-summarization`
- Testing: `#alpha-builds`, `#bug-reports`, `#perf-testing`
- Documentation: `#docs-feedback`, `#examples`, `#tutorials`

## Development

```bash
git clone https://github.com/bjornefisk/gitreleasegen.git
cd gitreleasegen
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Lint and format
ruff check .
ruff format .

# Run tests with coverage
pytest --cov=gitreleasegen
```

## Contributing

Contributions are welcome! Please open an issue to discuss major changes first. Make sure pre-commit hooks pass before submitting a pull request.

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
