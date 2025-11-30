"""Jinja2 template engine for changelog rendering."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import ChangeItem, Changelog, ChangelogSection

# Default templates directory bundled with the package
DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Mapping of output formats to default template filenames
FORMAT_TEMPLATES = {
    "markdown": "markdown.j2",
    "html": "html.j2",
    "text": "text.j2",
    "json": "json.j2",
    "yaml": "yaml.j2",
}

# Extension to format mapping for auto-detection
EXTENSION_FORMAT_MAP = {
    ".md.j2": "markdown",
    ".markdown.j2": "markdown",
    ".html.j2": "html",
    ".htm.j2": "html",
    ".txt.j2": "text",
    ".text.j2": "text",
    ".json.j2": "json",
    ".yaml.j2": "yaml",
    ".yml.j2": "yaml",
}


def _slugify(value: str) -> str:
    """Convert a string to a URL-friendly slug."""
    return "-".join(
        filter(None, "".join(ch.lower() if ch.isalnum() else " " for ch in value).split())
    )


def _escape_md(value: str) -> str:
    """Escape special Markdown characters."""
    chars_to_escape = r"\`*_{}[]()#+-.!|"
    pattern = f"([{re.escape(chars_to_escape)}])"
    return re.sub(pattern, r"\\\1", value)


def _date_format(value: Optional[datetime], fmt: str = "%Y-%m-%d") -> str:
    """Format a datetime object to string."""
    if value is None:
        return ""
    return value.strftime(fmt)


def _truncate_text(value: str, length: int = 80, ellipsis: str = "...") -> str:
    """Truncate text to a maximum length."""
    if len(value) <= length:
        return value
    return value[: length - len(ellipsis)] + ellipsis


def _short_sha(value: str, length: int = 7) -> str:
    """Return the first N characters of a SHA hash."""
    return value[:length] if value else ""


def _item_to_dict(item: ChangeItem) -> Dict[str, Any]:
    """Convert a ChangeItem to a dictionary for template context."""
    return {
        "title": item.title,
        "type": item.type,
        "scope": item.scope,
        "breaking": item.breaking,
        "summary": item.summary,
        "details": item.details,
        "notes": list(item.notes),
        "references": dict(item.references),
        "metadata": dict(item.metadata) if item.metadata else {},
    }


def _section_to_dict(section: ChangelogSection) -> Dict[str, Any]:
    """Convert a ChangelogSection to a dictionary for template context."""
    return {
        "title": section.title,
        "slug": _slugify(section.title),
        "changes": [_item_to_dict(item) for item in section.items],
    }


def changelog_to_context(changelog: Changelog) -> Dict[str, Any]:
    """Convert a Changelog object to a template context dictionary.

    Args:
        changelog: The Changelog object to convert.

    Returns:
        A dictionary suitable for use as Jinja2 template context.
    """
    return {
        "changelog": {
            "version": changelog.version,
            "date": changelog.date,
            "date_formatted": _date_format(changelog.date) if changelog.date else None,
            "sections": [_section_to_dict(section) for section in changelog.sections],
            "metadata": dict(changelog.metadata) if changelog.metadata else {},
        },
        "now": datetime.now(),
    }


class TemplateEngine:
    """Jinja2 template engine for rendering changelogs."""

    def __init__(
        self,
        custom_templates_dir: Optional[Path] = None,
        autoescape_formats: tuple[str, ...] = ("html", "htm", "xml"),
    ) -> None:
        """Initialize the template engine.

        Args:
            custom_templates_dir: Optional directory for custom templates.
                If provided, templates from this directory take precedence.
            autoescape_formats: File extensions that should have autoescaping enabled.
        """
        # Build list of template directories (custom first, then defaults)
        template_dirs = []
        if custom_templates_dir and custom_templates_dir.is_dir():
            template_dirs.append(str(custom_templates_dir))
        template_dirs.append(str(DEFAULT_TEMPLATES_DIR))

        self.env = Environment(
            loader=FileSystemLoader(template_dirs),
            autoescape=select_autoescape(autoescape_formats),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # Register custom filters
        self.env.filters["date_format"] = _date_format
        self.env.filters["truncate_text"] = _truncate_text
        self.env.filters["slugify"] = _slugify
        self.env.filters["escape_md"] = _escape_md
        self.env.filters["short_sha"] = _short_sha
        self.env.filters["escape_html"] = html.escape

    def render(
        self,
        changelog: Changelog,
        output_format: str,
        template_path: Optional[Path] = None,
    ) -> str:
        """Render a changelog using Jinja2 templates.

        Args:
            changelog: The Changelog object to render.
            output_format: The output format (markdown, html, text, json, yaml).
            template_path: Optional path to a custom template file.
                If provided, this template is used instead of the default.

        Returns:
            The rendered changelog as a string.

        Raises:
            ValueError: If the output format is not supported.
            FileNotFoundError: If the template file is not found.
        """
        context = changelog_to_context(changelog)

        if template_path:
            # Load template from absolute path
            template_path = Path(template_path).resolve()
            if not template_path.is_file():
                raise FileNotFoundError(f"Template not found: {template_path}")

            # Create a new loader for this specific template
            loader = FileSystemLoader(str(template_path.parent))
            env = self.env.overlay(loader=loader)
            template = env.get_template(template_path.name)
        else:
            # Use default template for the format
            template_name = FORMAT_TEMPLATES.get(output_format)
            if not template_name:
                raise ValueError(f"Unsupported output format: {output_format}")
            template = self.env.get_template(template_name)

        return template.render(**context)

    def render_from_file(
        self,
        changelog: Changelog,
        template_path: Path,
    ) -> str:
        """Render a changelog using a specific template file.

        Args:
            changelog: The Changelog object to render.
            template_path: Path to the template file.

        Returns:
            The rendered changelog as a string.
        """
        context = changelog_to_context(changelog)
        template_path = Path(template_path).resolve()

        if not template_path.is_file():
            raise FileNotFoundError(f"Template not found: {template_path}")

        loader = FileSystemLoader(str(template_path.parent))
        env = self.env.overlay(loader=loader)
        template = env.get_template(template_path.name)

        return template.render(**context)


def detect_format_from_template(template_path: Path) -> Optional[str]:
    """Detect the output format from a template file path.

    Args:
        template_path: Path to the template file.

    Returns:
        The detected format (markdown, html, text, json, yaml), or None if unknown.
    """
    name = template_path.name.lower()

    # Check for known double extensions
    for ext, fmt in EXTENSION_FORMAT_MAP.items():
        if name.endswith(ext):
            return fmt

    # Fall back to single extension check
    if name.endswith(".j2") or name.endswith(".jinja2"):
        stem = template_path.stem.lower()
        if stem in FORMAT_TEMPLATES:
            return stem
        # Check if stem ends with format name
        for fmt in FORMAT_TEMPLATES:
            if stem.endswith(fmt):
                return fmt

    return None


# Module-level engine instance for convenience
_default_engine: Optional[TemplateEngine] = None


def get_default_engine() -> TemplateEngine:
    """Get or create the default template engine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = TemplateEngine()
    return _default_engine


def render_template(
    changelog: Changelog,
    output_format: str,
    template_path: Optional[Path] = None,
) -> str:
    """Render a changelog using the default template engine.

    This is a convenience function that uses a module-level engine instance.

    Args:
        changelog: The Changelog object to render.
        output_format: The output format (markdown, html, text, json, yaml).
        template_path: Optional path to a custom template file.

    Returns:
        The rendered changelog as a string.
    """
    engine = get_default_engine()
    return engine.render(changelog, output_format, template_path)


__all__ = [
    "DEFAULT_TEMPLATES_DIR",
    "FORMAT_TEMPLATES",
    "TemplateEngine",
    "changelog_to_context",
    "detect_format_from_template",
    "get_default_engine",
    "render_template",
]

