---
layout: default
title: Installation
nav_order: 2
---

# Installation

Requires Python 3.9+.

## From PyPI

```bash
pip install gitreleasegen
```

Verify:

```bash
gitreleasegen --help
```

## From source (development)

```bash
git clone https://github.com/bjornefisk/gitreleasegen.git
cd gitreleasegen
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

