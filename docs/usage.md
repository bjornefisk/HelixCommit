---
layout: default
title: Usage
nav_order: 3
---

# Usage

GitReleaseGen ships a CLI and Python API.

## CLI

```bash
gitreleasegen generate [OPTIONS]
```

### Options

**Ranges:**
- `--repo PATH` - repository path (default: current dir)
- `--since-tag TAG` / `--until-tag TAG` - tag-based range
- `--since REF` / `--until REF` - any Git ref
- `--unreleased` - latest tag to HEAD

**Output:**
- `--format {markdown,html,text}` - default: markdown
- `--out PATH` - write to file instead of stdout

**Filtering:**
- `--no-prs` - skip GitHub PR lookups
- `--no-merge-commits` - exclude merge commits
- `--max-items INT` - limit commits processed
- `--fail-on-empty` - exit 1 if no commits found

### Examples
```bash
# between tags
gitreleasegen generate --since-tag v1.4.0 --until-tag v1.5.0 --out v1.5.0.md

# unreleased
gitreleasegen generate --unreleased --no-prs

# with AI (OpenAI)
export OPENAI_API_KEY=sk-...
gitreleasegen generate --unreleased --use-llm --openai-model gpt-4o-mini

# with AI (OpenRouter)
export OPENROUTER_API_KEY=or-...
gitreleasegen generate --use-llm --llm-provider openrouter
```

## Python API

```python
from datetime import datetime
from pathlib import Path
from gitreleasegen.changelog import ChangelogBuilder
from gitreleasegen.git_client import CommitRange, GitRepository
from gitreleasegen.formatters import markdown

repo = GitRepository(Path("."))
commits = list(repo.iter_commits(CommitRange(since="v1.4.0", until="v1.5.0")))

builder = ChangelogBuilder(include_scopes=True)
changelog = builder.build(
    version="v1.5.0",
    release_date=datetime.utcnow(),
    commits=commits,
    commit_prs={},
    pr_index={},
)

print(markdown.render_markdown(changelog))
```


## Prompt engineering (when LLMs are enabled)

When you pass `--use-llm`, GitReleaseGen runs a prompt-engineering pipeline:

```bash
gitreleasegen generate \
    --use-llm \
    --domain-scope "conservation" \
    --expert-role "Product Manager" \
    --expert-role "Tech Lead" \
    --expert-role "QA Engineer" \
    --rag-backend simple
```

When enabled, the pipeline includes:

- Domain-scoped system prompt (`--domain-scope`) to constrain tone and norms.
- Multi-expert role prompting (repeat `--expert-role` to add perspectives; defaults include Product Manager, Tech Lead, QA Engineer).
- Lightweight RAG with query planning over commit and PR text. Choose the retrieval engine with `--rag-backend` (`simple` by default; `chroma` if you have `chromadb` installed).
- Self-critique final editing pass for clarity and brevity.

Adjust inputs such as domain scope or expert roles to influence tone. Change the cache path to force regeneration when needed. Note that enabling LLMs increases token usage relative to a single-pass summarizer.

