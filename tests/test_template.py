"""Tests for the Jinja2 template engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from helixcommit.models import ChangeItem, Changelog, ChangelogSection
from helixcommit.template import (
    DEFAULT_TEMPLATES_DIR,
    FORMAT_TEMPLATES,
    TemplateEngine,
    changelog_to_context,
    detect_format_from_template,
    render_template,
)


@pytest.fixture
def sample_changelog() -> Changelog:
    """Create a sample changelog for testing."""
    items = [
        ChangeItem(
            title="Add new feature",
            type="feat",
            scope="api",
            breaking=False,
            summary="Added a new feature to the API",
            details="This is a detailed description.",
            notes=[],
            references={"commit": "abc1234def", "pr": "https://github.com/test/repo/pull/1"},
            metadata={"pr_number": "1", "authors": ["user1"]},
        ),
        ChangeItem(
            title="Fix critical bug",
            type="fix",
            scope=None,
            breaking=True,
            summary="Fixed a critical bug",
            details=None,
            notes=["API signature changed"],
            references={"commit": "def5678abc"},
            metadata={"authors": ["user2"]},
        ),
    ]
    sections = [
        ChangelogSection(title="Features", items=[items[0]]),
        ChangelogSection(title="Bug Fixes", items=[items[1]]),
    ]
    return Changelog(
        version="1.0.0",
        date=datetime(2024, 1, 15, 12, 0, 0),
        sections=sections,
        metadata={"compare_url": "https://github.com/test/repo/compare/v0.9.0...v1.0.0"},
    )


class TestChangelogToContext:
    """Tests for changelog_to_context function."""

    def test_basic_structure(self, sample_changelog: Changelog) -> None:
        """Test that context has expected structure."""
        context = changelog_to_context(sample_changelog)

        assert "changelog" in context
        assert "now" in context
        assert isinstance(context["now"], datetime)

    def test_changelog_fields(self, sample_changelog: Changelog) -> None:
        """Test that changelog fields are properly converted."""
        context = changelog_to_context(sample_changelog)
        cl = context["changelog"]

        assert cl["version"] == "1.0.0"
        assert cl["date"] == sample_changelog.date
        assert cl["date_formatted"] == "2024-01-15"
        assert "compare_url" in cl["metadata"]

    def test_sections_conversion(self, sample_changelog: Changelog) -> None:
        """Test that sections are properly converted."""
        context = changelog_to_context(sample_changelog)
        sections = context["changelog"]["sections"]

        assert len(sections) == 2
        assert sections[0]["title"] == "Features"
        assert sections[0]["slug"] == "features"
        assert len(sections[0]["changes"]) == 1

    def test_item_fields(self, sample_changelog: Changelog) -> None:
        """Test that change items are properly converted."""
        context = changelog_to_context(sample_changelog)
        item = context["changelog"]["sections"][0]["changes"][0]

        assert item["title"] == "Add new feature"
        assert item["type"] == "feat"
        assert item["scope"] == "api"
        assert item["breaking"] is False
        assert item["summary"] == "Added a new feature to the API"
        assert "pr" in item["references"]
        assert item["metadata"]["pr_number"] == "1"

    def test_none_date_handling(self) -> None:
        """Test handling of None date."""
        changelog = Changelog(version="1.0.0", date=None, sections=[])
        context = changelog_to_context(changelog)

        assert context["changelog"]["date"] is None
        assert context["changelog"]["date_formatted"] is None


class TestTemplateEngine:
    """Tests for TemplateEngine class."""

    def test_default_templates_exist(self) -> None:
        """Test that all default templates exist."""
        for template_name in FORMAT_TEMPLATES.values():
            template_path = DEFAULT_TEMPLATES_DIR / template_name
            assert template_path.exists(), f"Missing template: {template_name}"

    def test_render_markdown(self, sample_changelog: Changelog) -> None:
        """Test rendering with default markdown template."""
        engine = TemplateEngine()
        output = engine.render(sample_changelog, "markdown")

        assert "## Release 1.0.0" in output
        assert "### Features" in output
        assert "Add new feature" in output
        assert "**api**" in output

    def test_render_html(self, sample_changelog: Changelog) -> None:
        """Test rendering with default html template."""
        engine = TemplateEngine()
        output = engine.render(sample_changelog, "html")

        assert '<section class="changelog">' in output
        assert "<h2>Release 1.0.0</h2>" in output
        assert "<h3>Features</h3>" in output

    def test_render_text(self, sample_changelog: Changelog) -> None:
        """Test rendering with default text template."""
        engine = TemplateEngine()
        output = engine.render(sample_changelog, "text")

        assert "Release 1.0.0" in output
        assert "FEATURES" in output
        assert "[api]" in output

    def test_render_json(self, sample_changelog: Changelog) -> None:
        """Test rendering with default json template."""
        engine = TemplateEngine()
        output = engine.render(sample_changelog, "json")

        assert '"version": "1.0.0"' in output
        assert '"title": "Add new feature"' in output

    def test_render_yaml(self, sample_changelog: Changelog) -> None:
        """Test rendering with default yaml template."""
        engine = TemplateEngine()
        output = engine.render(sample_changelog, "yaml")

        assert 'version: "1.0.0"' in output
        assert 'title: "Add new feature"' in output

    def test_unsupported_format(self, sample_changelog: Changelog) -> None:
        """Test that unsupported format raises ValueError."""
        engine = TemplateEngine()

        with pytest.raises(ValueError, match="Unsupported output format"):
            engine.render(sample_changelog, "unsupported")

    def test_custom_template(self, sample_changelog: Changelog, tmp_path: Path) -> None:
        """Test rendering with a custom template."""
        custom_template = tmp_path / "custom.j2"
        custom_template.write_text(
            "Version: {{ changelog.version }}\n"
            "Sections: {{ changelog.sections | length }}"
        )

        engine = TemplateEngine()
        output = engine.render(sample_changelog, "markdown", template_path=custom_template)

        assert "Version: 1.0.0" in output
        assert "Sections: 2" in output

    def test_custom_template_not_found(self, sample_changelog: Changelog, tmp_path: Path) -> None:
        """Test that missing custom template raises FileNotFoundError."""
        missing_template = tmp_path / "nonexistent.j2"
        engine = TemplateEngine()

        with pytest.raises(FileNotFoundError, match="Template not found"):
            engine.render(sample_changelog, "markdown", template_path=missing_template)


class TestDetectFormatFromTemplate:
    """Tests for detect_format_from_template function."""

    def test_markdown_extensions(self) -> None:
        """Test detection of markdown format."""
        assert detect_format_from_template(Path("changelog.md.j2")) == "markdown"
        assert detect_format_from_template(Path("changelog.markdown.j2")) == "markdown"

    def test_html_extensions(self) -> None:
        """Test detection of html format."""
        assert detect_format_from_template(Path("changelog.html.j2")) == "html"
        assert detect_format_from_template(Path("changelog.htm.j2")) == "html"

    def test_text_extensions(self) -> None:
        """Test detection of text format."""
        assert detect_format_from_template(Path("changelog.txt.j2")) == "text"
        assert detect_format_from_template(Path("changelog.text.j2")) == "text"

    def test_json_extension(self) -> None:
        """Test detection of json format."""
        assert detect_format_from_template(Path("changelog.json.j2")) == "json"

    def test_yaml_extensions(self) -> None:
        """Test detection of yaml format."""
        assert detect_format_from_template(Path("changelog.yaml.j2")) == "yaml"
        assert detect_format_from_template(Path("changelog.yml.j2")) == "yaml"

    def test_unknown_format(self) -> None:
        """Test that unknown format returns None."""
        assert detect_format_from_template(Path("changelog.xyz.j2")) is None

    def test_stem_based_detection(self) -> None:
        """Test detection based on template stem name."""
        assert detect_format_from_template(Path("markdown.j2")) == "markdown"
        assert detect_format_from_template(Path("html.j2")) == "html"


class TestRenderTemplate:
    """Tests for render_template convenience function."""

    def test_basic_render(self, sample_changelog: Changelog) -> None:
        """Test that render_template works correctly."""
        output = render_template(sample_changelog, "markdown")

        assert "## Release 1.0.0" in output
        assert "Add new feature" in output


class TestCustomFilters:
    """Tests for custom Jinja2 filters."""

    def test_short_sha_filter(self, sample_changelog: Changelog) -> None:
        """Test that short_sha filter works in templates."""
        engine = TemplateEngine()
        output = engine.render(sample_changelog, "markdown")

        # Should contain short SHA (7 chars)
        assert "abc1234" in output

    def test_slugify_filter(self, sample_changelog: Changelog) -> None:
        """Test that slugify filter works in templates."""
        engine = TemplateEngine()
        output = engine.render(sample_changelog, "html")

        # Slugified section title
        assert "changelog-section--features" in output
        assert "changelog-section--bug-fixes" in output

    def test_escape_html_filter(self, sample_changelog: Changelog) -> None:
        """Test that escape_html filter works in templates."""
        # Create changelog with HTML-unsafe content
        items = [
            ChangeItem(
                title="Fix <script>alert('xss')</script> issue",
                type="fix",
                scope=None,
                breaking=False,
            )
        ]
        changelog = Changelog(
            version="1.0.0",
            date=datetime.now(),
            sections=[ChangelogSection(title="Bug Fixes", items=items)],
        )

        engine = TemplateEngine()
        output = engine.render(changelog, "html")

        # Should escape HTML entities
        assert "&lt;script&gt;" in output
        assert "<script>" not in output


class TestEmptyChangelog:
    """Tests for rendering empty changelogs."""

    def test_empty_sections(self) -> None:
        """Test rendering changelog with no sections."""
        changelog = Changelog(
            version="1.0.0",
            date=datetime(2024, 1, 15),
            sections=[],
        )

        engine = TemplateEngine()

        for fmt in ["markdown", "html", "text", "json", "yaml"]:
            output = engine.render(changelog, fmt)
            assert "1.0.0" in output

    def test_empty_items(self) -> None:
        """Test rendering section with no items."""
        changelog = Changelog(
            version="1.0.0",
            date=datetime(2024, 1, 15),
            sections=[ChangelogSection(title="Features", items=[])],
        )

        engine = TemplateEngine()
        output = engine.render(changelog, "markdown")

        assert "1.0.0" in output

