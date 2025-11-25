import json
from unittest.mock import MagicMock, patch

import pytest

from helixcommit.summarizer import (
    OpenAISummarizer,
    PromptEngineeredSummarizer,
    SummaryCache,
    SummaryRequest,
)


@pytest.fixture
def mock_openai():
    with patch("helixcommit.summarizer.OpenAI") as mock:
        yield mock

def test_summary_cache(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache = SummaryCache(cache_file)
    
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    
    # Verify persistence
    cache2 = SummaryCache(cache_file)
    assert cache2.get("key1") == "value1"

def test_openai_summarizer(mock_openai):
    # Setup mock response
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = json.dumps({
        "entries": [{"id": "1", "summary": "Summarized title"}]
    })
    mock_client.chat.completions.create.return_value = mock_completion
    
    summarizer = OpenAISummarizer(api_key="test")
    requests = [SummaryRequest(identifier="1", title="Original title")]
    
    results = list(summarizer.summarize(requests))
    
    assert len(results) == 1
    assert results[0].summary == "Summarized title"
    assert results[0].identifier == "1"

def test_prompt_engineered_summarizer(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    # Mock responses for multiple calls (experts, synthesis, critique)
    # We can just return a simple string for all of them
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "Polished summary"
    mock_client.chat.completions.create.return_value = mock_completion
    
    summarizer = PromptEngineeredSummarizer(
        api_key="test",
        expert_roles=["Expert"]
    )
    requests = [SummaryRequest(identifier="1", title="Original title", body=None)]
    
    results = list(summarizer.summarize(requests))
    
    assert len(results) == 1
    assert results[0].summary == "Polished summary"
