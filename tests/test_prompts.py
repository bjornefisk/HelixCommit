from helixcommit import prompts


def test_commit_prompt_contains_strict_rules():
    prompt = prompts.COMMIT_MESSAGE_SYSTEM_PROMPT
    assert "Output ONLY the commit message itself" in prompt
    assert "Start your response directly with the commit subject line" in prompt
    assert "Format: A subject line in imperative tone" in prompt
