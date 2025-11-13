---
layout: default
title: Contributing
nav_order: 6
---

# Contributing

## Setup

```bash
git clone https://github.com/bjornefisk/gitreleasegen.git
cd gitreleasegen
pip install -e ".[dev]"
pytest
```

## Workflow

- Create a feature branch
- Add tests for changes
- Run `pytest` before opening PR
- Use conventional commits

## PR Checklist

- [ ] Tests pass
- [ ] Docs updated if needed
- [ ] CI passes

