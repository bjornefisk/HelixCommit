---
layout: default
title: Configuration
nav_order: 4
---

# Configuration

Run `gitreleasegen generate --help` for all options.

## CLI options overview

| Area | Flag(s) | Description |
| --- | --- | --- |
| Commit range | `--since`, `--until`, `--since-tag`, `--until-tag`, `--unreleased` | Control which commits are included. |
| Output | `--format`, `--out` | Choose Markdown/HTML/text and write to a file if needed. |
| Filtering | `--no-merge-commits`, `--max-items` | Skip merge commits and cap the number of commits processed. |
| GitHub enrichment | `--no-prs`, `--github-token` | Toggle PR lookups and supply a token for private repos or higher rate limits. |
| LLM summaries | `--use-llm`, `--llm-provider`, `--openai-model`, `--openrouter-model`, `--summary-cache` | Enable AI summaries and control how responses are cached. |
| Failure handling | `--fail-on-empty` | Exit with status code 1 when no changes are found. |

Use `gitreleasegen generate --help` to explore the full surface area.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `GITHUB_TOKEN` | Personal access token for GitHub API calls (optional but avoids rate limits). |
| `OPENAI_API_KEY` | Required when `--use-llm` with the OpenAI provider. |
| `OPENROUTER_API_KEY` | Required when `--use-llm --llm-provider openrouter`. |
| `GITRELEASEGEN_GH_MAX_RETRIES` | Override the number of GitHub API retries (default `3`). |
| `GITRELEASEGEN_GH_BACKOFF_BASE_SEC` | Base delay (seconds) for exponential backoff (default `0.5`). |
| `GITRELEASEGEN_GH_BACKOFF_CAP_SEC` | Maximum backoff delay (seconds) for retries (default `8`). |
| `GITRELEASEGEN_GH_CACHE` | Enable the on-disk GitHub cache when set to `1`, `true`, `yes`, or `on`. Disabled by default. |
| `GITRELEASEGEN_GH_CACHE_DIR` | Directory where GitHub cache files are stored (default `.gitreleasegen-cache/github`). |
| `GITRELEASEGEN_GH_CACHE_TTL_MINUTES` / `GITRELEASEGEN_GH_CACHE_TTL_SECONDS` | Configure the cache time-to-live (default 10 minutes). |

Environment variables act as fallbacks where supported—you can override them per invocation via CLI flags.

### GitHub retries and caching

GitHub calls automatically retry on transient failures (timeouts, HTTP 5xx) using exponential backoff with jitter. Receiving a rate-limit response (HTTP 429 or `403` with `X-RateLimit-Remaining: 0`) is handled by observing GitHub’s `Retry-After` or `X-RateLimit-Reset` headers before retrying. After the configured retry budget is exhausted, a `GitHubRateLimitError` or `GitHubApiError` is raised.

To reduce duplicate API traffic you can opt in to an on-disk cache for pull request lookups by setting `GITRELEASEGEN_GH_CACHE=1`. Cached entries are stored as JSON and reused until their TTL expires; adjust the location and lifetime with the environment variables above. Each run still keeps an in-memory cache so repeated requests within a single execution remain fast even with caching disabled.

## Custom templates

HTML, Markdown, and text output are rendered through dedicated formatters located in `gitreleasegen/formatters`. To bring your own look-and-feel:

1. Copy the relevant template (Markdown defaults to `markdown.py` with Jinja2 templates under `formatters/markdown`).
2. Point `ChangelogBuilder` at your custom renderer, or fork the formatter module and use it in your integration.
3. Optionally add a CLI wrapper that pipes the generated changelog into your formatter for reuse across teams.

`GeneratorConfig` in `gitreleasegen.config` exposes higher-level configuration if you prefer constructing changelog runs programmatically.

## GitHub API setup

When run against GitHub repos, GitReleaseGenerator can attach PR metadata, authors, and compare links.

1. Create a personal access token with `repo` scope (classic) or `contents`+`pull_requests` (fine-grained).
2. Store it as `GITHUB_TOKEN` in your shell or CI secret manager.
3. Pass `--github-token $GITHUB_TOKEN` (the CLI will also detect the env var automatically).

For private repositories you must supply a token; public repositories will work without one but may hit unauthenticated rate limits.

