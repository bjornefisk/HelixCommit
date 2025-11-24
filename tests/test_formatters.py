from datetime import datetime

from helixcommit.formatters.html import render_html
from helixcommit.formatters.markdown import render_markdown
from helixcommit.formatters.text import render_text
from helixcommit.models import ChangeItem, Changelog, ChangelogSection


def build_sample_changelog() -> Changelog:
    item = ChangeItem(
        title="Add OAuth login",
        type="feat",
        scope="auth",
        breaking=False,
        summary="Add OAuth login",
        details="Supports Google and GitHub providers.",
        references={"pr": "https://github.com/example/project/pull/1", "commit": "abc1234"},
        metadata={"pr_number": "1"},
    )
    section = ChangelogSection(title="Features", items=[item])
    return Changelog(
        version="1.0.0",
        date=datetime(2024, 7, 1),
        sections=[section],
        metadata={"compare_url": "https://github.com/example/project/compare/v0.9.0...v1.0.0"},
    )


def test_render_markdown_contains_references():
    changelog = build_sample_changelog()
    md = render_markdown(changelog)

    assert "## Release 1.0.0" in md
    assert "[#1](https://github.com/example/project/pull/1)" in md
    assert "Supports Google" in md
    assert "[auth]" not in md  # ensure scope formatting uses bold prefix


def test_render_html_structure():
    changelog = build_sample_changelog()
    html = render_html(changelog)

    assert '<section class="changelog">' in html
    assert "<h3>Features</h3>" in html
    assert "Add OAuth login" in html
    assert "compare/v0.9.0...v1.0.0" in html


def test_render_text_plain_output():
    changelog = build_sample_changelog()
    text_output = render_text(changelog)

    assert "Release 1.0.0" in text_output
    assert "PR #1" in text_output
    assert "Supports Google" in text_output
