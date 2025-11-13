# Contributing to GitReleaseGen

Thank you for your interest in contributing to GitReleaseGen! This document provides guidelines and instructions for contributing.

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Git
- (Optional) GitHub account for pull request contributions

### Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/yourusername/gitreleasegen.git
   cd gitreleasegen
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install development dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Install pre-commit hooks (optional but recommended):**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=gitreleasegen --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_parser.py

# Run with verbose output
pytest -v
```

### Code Quality

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Run linter
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

### Type Checking

While not strictly enforced, we encourage type hints:

```bash
# Install mypy if needed
pip install mypy

# Run type checker
mypy src/gitreleasegen
```

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/your-feature-name` for new features
- `fix/bug-description` for bug fixes
- `docs/what-changed` for documentation updates
- `refactor/area-improved` for refactoring

### Commit Messages

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes

**Examples:**
```
feat(summarizer): add support for Claude API
fix(parser): handle edge case in footer parsing
docs: update installation instructions
test(grouper): add tests for deduplication logic
```

### Pull Request Process

1. **Update your fork:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make your changes:**
   - Write clean, readable code
   - Add tests for new functionality
   - Update documentation as needed
   - Ensure all tests pass
   - Follow the existing code style

3. **Create a pull request:**
   - Use a clear, descriptive title
   - Reference any related issues
   - Provide a detailed description of changes
   - Include screenshots for UI changes
   - List any breaking changes

4. **Code review:**
   - Address reviewer feedback promptly
   - Keep discussions focused and professional
   - Be open to suggestions

## Testing Guidelines

### Writing Tests

- Place tests in the `tests/` directory
- Mirror the source structure (e.g., `test_parser.py` for `parser.py`)
- Use descriptive test names: `test_<functionality>_<scenario>`
- Include docstrings for complex tests
- Test both happy paths and edge cases

**Example:**
```python
def test_parse_conventional_commit_with_breaking_footer():
    """Verify breaking change detection from BREAKING CHANGE footer."""
    message = "feat!: new feature\n\nBREAKING CHANGE: API changed"
    parsed = parse_commit_message(message)
    
    assert parsed.breaking is True
    assert "API changed" in parsed.breaking_descriptions
```

### Test Coverage

- Aim for >80% coverage on new code
- Critical paths should have >95% coverage
- Don't sacrifice test quality for coverage metrics

## Documentation

### Code Documentation

- Add docstrings to all public modules, classes, and functions
- Use Google-style docstrings:

```python
def parse_commit_message(message: str) -> ParsedCommitMessage:
    """Parse a commit message into Conventional Commit components.
    
    Args:
        message: The raw commit message to parse.
        
    Returns:
        A ParsedCommitMessage containing all parsed components.
        
    Example:
        >>> parsed = parse_commit_message("feat(auth): add OAuth")
        >>> parsed.type
        'feat'
    """
```

### User Documentation

- Update `README.md` for user-facing changes
- Add examples to `examples/` directory
- Update `docs/` for architectural changes

## Adding New Features

### Feature Checklist

- [ ] Implemented with clean, tested code
- [ ] Added comprehensive tests
- [ ] Updated relevant documentation
- [ ] Added example usage
- [ ] Considered backward compatibility
- [ ] Updated CHANGELOG.md
- [ ] No breaking changes (or clearly documented)

### Breaking Changes

If your change breaks backward compatibility:
1. Justify why it's necessary
2. Provide a migration guide
3. Update the major version number
4. Add `BREAKING CHANGE:` footer in commit

## Project Structure

```
gitreleasegen/
├── src/gitreleasegen/      # Source code
│   ├── cli.py              # Command-line interface
│   ├── git_client.py       # Git operations
│   ├── github_client.py    # GitHub API client
│   ├── parser.py           # Commit message parser
│   ├── grouper.py          # Change grouping logic
│   ├── changelog.py        # Changelog builder
│   ├── summarizer.py       # LLM summarization
│   ├── models.py           # Data models
│   └── formatters/         # Output formatters
├── tests/                  # Test suite
├── docs/                   # Documentation
├── examples/               # Usage examples
└── pyproject.toml          # Project configuration
```

## Getting Help

- **Questions:** Open a [Discussion](https://github.com/yourusername/gitreleasegen/discussions)
- **Bugs:** File an [Issue](https://github.com/yourusername/gitreleasegen/issues)
- **Security:** See [SECURITY.md](SECURITY.md)

## Release Process

Maintainers follow this process for releases:

1. Update version in `pyproject.toml` and `__init__.py`
2. Update `CHANGELOG.md` with release notes
3. Create a git tag: `git tag -a v1.0.0 -m "Release 1.0.0"`
4. Push tag: `git push origin v1.0.0`
5. GitHub Actions will build and publish to PyPI

## Recognition

Contributors will be recognized in:
- Release notes
- Repository contributors list
- Special thanks in documentation

Thank you for contributing! 🎉
