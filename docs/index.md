---
layout: default
title: Home
nav_order: 1
---

# GitReleaseGen

**Current Version:** `0.1.0`

Automated release notes from Git history. Reads commits, groups them by type, optionally fetches GitHub PR data, and outputs Markdown/HTML/text.

## Features

- Groups commits by type with automatic PR linking
- Markdown, HTML, and plaintext output
- Optional AI summaries (OpenAI/OpenRouter)
- CLI and Python API

## Install

```bash
pip install gitreleasegen
```

## Quick Start

```bash
# Zero-config run (offline-friendly)
gitreleasegen generate --unreleased --no-prs --format markdown > RELEASE_NOTES.md

# Specific range
gitreleasegen generate --since-tag v1.4.0 --until-tag v1.5.0 --format html --out notes.html
```

See Installation and Usage pages for more details.

