from helixcommit.parser import classify_change_type, parse_commit_message


def test_parse_conventional_commit_with_breaking_footer():
    message = (
        "feat(auth)!: require MFA\n\n"
        "Introduce mandatory multi-factor authentication for admin users.\n\n"
        "BREAKING CHANGE: Admin users must configure MFA before the next login.\n"
        "Refs: #123"
    )
    parsed = parse_commit_message(message)

    assert parsed.type == "feat"
    assert parsed.scope == "auth"
    assert parsed.breaking is True
    assert parsed.breaking_descriptions == ["Admin users must configure MFA before the next login."]
    assert parsed.footers["Refs"] == ["#123"]
    assert parsed.body.startswith("Introduce mandatory")


def test_parse_non_conventional_commit_returns_defaults():
    message = "Release v1.2.3"
    parsed = parse_commit_message(message)

    assert parsed.type is None
    assert parsed.subject == "Release v1.2.3"
    assert parsed.breaking is False


def test_classify_change_type_heuristics():
    assert classify_change_type("Fix flaky tests in pipeline") == "test"
    assert classify_change_type("Improve performance of data loader") == "perf"
    assert classify_change_type("Document new configuration") == "docs"
