import json
from datetime import datetime, timezone

from helixcommit.formatters.html import render_html
from helixcommit.formatters.json import render_json
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


# JSON formatter tests


def test_render_json_valid_json():
    """Test that render_json produces valid JSON."""
    changelog = build_sample_changelog()
    json_output = render_json(changelog)

    # Should parse without error
    data = json.loads(json_output)
    assert isinstance(data, dict)


def test_render_json_structure():
    """Test that JSON output has the correct top-level structure."""
    changelog = build_sample_changelog()
    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert "version" in data
    assert "date" in data
    assert "sections" in data
    assert "metadata" in data

    assert data["version"] == "1.0.0"
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) == 1


def test_render_json_section_structure():
    """Test that sections have the correct structure."""
    changelog = build_sample_changelog()
    json_output = render_json(changelog)
    data = json.loads(json_output)

    section = data["sections"][0]
    assert section["title"] == "Features"
    assert isinstance(section["items"], list)
    assert len(section["items"]) == 1


def test_render_json_item_fields():
    """Test that change items have all expected fields."""
    changelog = build_sample_changelog()
    json_output = render_json(changelog)
    data = json.loads(json_output)

    item = data["sections"][0]["items"][0]

    assert item["title"] == "Add OAuth login"
    assert item["type"] == "feat"
    assert item["scope"] == "auth"
    assert item["breaking"] is False
    assert item["summary"] == "Add OAuth login"
    assert item["details"] == "Supports Google and GitHub providers."
    assert item["notes"] == []
    assert item["references"]["pr"] == "https://github.com/example/project/pull/1"
    assert item["references"]["commit"] == "abc1234"
    assert item["metadata"]["pr_number"] == "1"


def test_render_json_datetime_serialization():
    """Test that datetime is serialized as ISO 8601 string."""
    changelog = build_sample_changelog()
    json_output = render_json(changelog)
    data = json.loads(json_output)

    # Should be ISO 8601 format
    assert data["date"] == "2024-07-01T00:00:00"


def test_render_json_datetime_with_timezone():
    """Test that timezone-aware datetime is serialized correctly."""
    item = ChangeItem(
        title="Test item",
        type="fix",
        scope=None,
        breaking=False,
    )
    section = ChangelogSection(title="Bug Fixes", items=[item])
    changelog = Changelog(
        version="2.0.0",
        date=datetime(2024, 12, 25, 10, 30, 0, tzinfo=timezone.utc),
        sections=[section],
    )

    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert data["date"] == "2024-12-25T10:30:00+00:00"


def test_render_json_null_date():
    """Test that None date is serialized as null."""
    item = ChangeItem(
        title="Test item",
        type="feat",
        scope=None,
        breaking=False,
    )
    section = ChangelogSection(title="Features", items=[item])
    changelog = Changelog(
        version="Unreleased",
        date=None,
        sections=[section],
    )

    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert data["date"] is None


def test_render_json_metadata():
    """Test that metadata is included in output."""
    changelog = build_sample_changelog()
    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert data["metadata"]["compare_url"] == "https://github.com/example/project/compare/v0.9.0...v1.0.0"


def test_render_json_breaking_change():
    """Test that breaking changes are correctly marked."""
    item = ChangeItem(
        title="Remove deprecated API",
        type="feat",
        scope="api",
        breaking=True,
        notes=["This removes the v1 API endpoints"],
    )
    section = ChangelogSection(title="Breaking Changes", items=[item])
    changelog = Changelog(
        version="3.0.0",
        date=datetime(2024, 1, 1),
        sections=[section],
    )

    json_output = render_json(changelog)
    data = json.loads(json_output)

    item_data = data["sections"][0]["items"][0]
    assert item_data["breaking"] is True
    assert item_data["notes"] == ["This removes the v1 API endpoints"]


def test_render_json_multiple_sections():
    """Test changelog with multiple sections."""
    feat_item = ChangeItem(
        title="New feature",
        type="feat",
        scope=None,
        breaking=False,
    )
    fix_item = ChangeItem(
        title="Bug fix",
        type="fix",
        scope="core",
        breaking=False,
    )
    feat_section = ChangelogSection(title="Features", items=[feat_item])
    fix_section = ChangelogSection(title="Bug Fixes", items=[fix_item])
    changelog = Changelog(
        version="1.1.0",
        date=datetime(2024, 6, 15),
        sections=[feat_section, fix_section],
    )

    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert len(data["sections"]) == 2
    assert data["sections"][0]["title"] == "Features"
    assert data["sections"][1]["title"] == "Bug Fixes"


def test_render_json_empty_sections():
    """Test changelog with empty sections list."""
    changelog = Changelog(
        version="0.0.1",
        date=datetime(2024, 1, 1),
        sections=[],
    )

    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert data["sections"] == []


def test_render_json_custom_indent():
    """Test that custom indentation is applied."""
    changelog = build_sample_changelog()

    # Test with 4-space indent
    json_output_4 = render_json(changelog, indent=4)
    assert "    " in json_output_4  # 4 spaces

    # Test with no indent (compact)
    json_output_none = render_json(changelog, indent=None)
    assert "\n" not in json_output_none  # No newlines = compact


def test_render_json_null_scope():
    """Test that null scope is correctly serialized."""
    item = ChangeItem(
        title="Global change",
        type="chore",
        scope=None,
        breaking=False,
    )
    section = ChangelogSection(title="Chores", items=[item])
    changelog = Changelog(
        version="1.0.1",
        date=datetime(2024, 3, 15),
        sections=[section],
    )

    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert data["sections"][0]["items"][0]["scope"] is None


def test_render_json_unicode_content():
    """Test that unicode characters are preserved."""
    item = ChangeItem(
        title="Add emoji support 🎉",
        type="feat",
        scope="ui",
        breaking=False,
        summary="Emojis work now! 👍",
    )
    section = ChangelogSection(title="Features", items=[item])
    changelog = Changelog(
        version="1.2.0",
        date=datetime(2024, 4, 1),
        sections=[section],
    )

    json_output = render_json(changelog)
    data = json.loads(json_output)

    assert "🎉" in data["sections"][0]["items"][0]["title"]
    assert "👍" in data["sections"][0]["items"][0]["summary"]
