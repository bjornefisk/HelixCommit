from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from helixcommit.cli import app

runner = CliRunner()

@pytest.fixture
def mock_git_repo():
    with patch("helixcommit.cli.GitRepository") as mock:
        repo_instance = MagicMock()
        mock.return_value = repo_instance
        yield repo_instance

@pytest.fixture
def mock_generator():
    with patch("helixcommit.cli.CommitGenerator") as mock:
        gen_instance = MagicMock()
        mock.return_value = gen_instance
        yield gen_instance

def test_generate_commit_no_staged_changes(mock_git_repo):
    # Setup: No staged changes
    mock_git_repo.get_diff.return_value = ""
    
    result = runner.invoke(app, ["generate-commit"])
    
    assert result.exit_code == 1
    assert "No staged changes found" in result.stdout

def test_generate_commit_success_flow(mock_git_repo, mock_generator):
    # Setup: Staged changes exist
    mock_git_repo.get_diff.return_value = "diff content"
    
    # Setup: Generator returns a message
    mock_generator.generate.return_value = "Feat: Add new feature"
    
    # Simulate user input: 'c' (commit) -> 'y' (confirm commit message)
    # Note: The CLI prompts for action [c/r/q], then confirms [y/n]
    result = runner.invoke(app, ["generate-commit", "--openrouter-api-key", "dummy"], input="c\ny\n")
    
    assert result.exit_code == 0
    assert "Analyzing changes..." in result.stdout
    assert "Feat: Add new feature" in result.stdout
    assert "Committed!" in result.stdout
    
    # Verify git commit was called
    mock_git_repo.commit.assert_called_once()
    args = mock_git_repo.commit.call_args[0][0]
    assert "Feat: Add new feature" in args
    # Check date format (MM-DD-YYYY)
    import re
    assert re.match(r"\d{2}-\d{2}-\d{4}: Feat: Add new feature", args)

def test_generate_commit_refine_flow(mock_git_repo, mock_generator):
    # Setup
    mock_git_repo.get_diff.return_value = "diff content"
    mock_generator.generate.return_value = "Initial bad message"
    mock_generator.chat.return_value = "Refined message"
    
    # Simulate: 'r' (reply) -> "Make it better" -> 'c' (commit) -> 'y' (confirm)
    result = runner.invoke(app, ["generate-commit", "--openrouter-api-key", "dummy"], input="r\nMake it better\nc\ny\n")
    
    assert result.exit_code == 0
    assert "Initial bad message" in result.stdout
    assert "Refined message" in result.stdout
    
    # Verify chat was called
    mock_generator.chat.assert_called_with("Make it better")
    
    # Verify commit
    mock_git_repo.commit.assert_called_once()
    args = mock_git_repo.commit.call_args[0][0]
    assert "Refined message" in args

def test_generate_commit_missing_api_key(mock_git_repo):
    # Setup: Staged changes exist so we pass the first check
    mock_git_repo.get_diff.return_value = "diff content"

    # Ensure no env vars are set for this test if possible, or just override
    with patch.dict("os.environ", {}, clear=True):
        result = runner.invoke(app, ["generate-commit", "--llm-provider", "openai"])
        assert result.exit_code == 1
        assert "Missing API key for openai" in result.stdout
