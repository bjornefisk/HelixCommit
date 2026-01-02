from helixcommit.commit_generator import CommitGenerator


def test_to_message_dedup_subject():
    # Create instance without running __init__ so we don't require an OpenAI client
    gen = CommitGenerator.__new__(CommitGenerator)

    text = (
        "feat: add login\n"
        "\n"
        "feat: add login\n"
        "\n"
        "- Add login form\n"
        "- Validate credentials"
    )

    cleaned = gen.to_message(text)

    assert cleaned.startswith("feat: add login")
    # The duplicated subject should be removed from the body
    assert "feat: add login\n\nfeat: add login" not in cleaned
    assert "- Add login form" in cleaned
    assert "Validate credentials" in cleaned
