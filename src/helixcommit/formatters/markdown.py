"""Markdown formatter for changelog output."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from ..models import ChangeItem, Changelog


def render_markdown(changelog: Changelog) -> str:
    """Render a changelog to Markdown."""

    lines: List[str] = []
    heading = _heading(changelog.version)
    lines.append(heading)
    if changelog.date:
        lines.append(_format_date(changelog.date))
    compare_url = changelog.metadata.get("compare_url") if changelog.metadata else None
    if compare_url:
        lines.append(f"[Compare changes]({compare_url})")
    lines.append("")

    for section in changelog.sections:
        if not section.items:
            continue
        lines.append(f"### {section.title}")
        for item in section.items:
            lines.extend(_render_item(item))
        lines.append("")

    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def _heading(version: Optional[str]) -> str:
    if version:
        return f"## Release {version}"
    return "## Release"


def _format_date(value: datetime) -> str:
    return f"_Released on {value.strftime('%Y-%m-%d')}_"


def _render_item(item: ChangeItem) -> List[str]:
    references = _format_references(item)
    scope_prefix = f"**{item.scope}** - " if item.scope else ""
    title_line = f"- {scope_prefix}{item.title}"
    if references:
        title_line = f"{title_line} {references}"
    lines = [title_line]
    if item.summary and item.summary != item.title:
        lines.append(f"  - _{item.summary}_")
    for note in item.notes:
        lines.append(f"  - BREAKING: {note}")
    if item.details:
        lines.extend(_render_blockquote(item.details))
    return lines


def _render_blockquote(text: str) -> Iterable[str]:
    for raw_line in text.splitlines():
        content = raw_line.rstrip()
        linestr = f"  > {content}" if content else "  >"
        yield linestr


def _format_references(item: ChangeItem) -> str:
    parts: List[str] = []
    pr_url = item.references.get("pr")
    pr_number = item.metadata.get("pr_number") if item.metadata else None
    if pr_url and pr_number:
        parts.append(f"[#{pr_number}]({pr_url})")
    commit_ref = item.references.get("commit")
    if commit_ref:
        commit_display = str(commit_ref)[:7]
        commit_url = item.references.get("commit_url")
        if commit_url and isinstance(commit_url, str) and commit_url.startswith("http"):
            parts.append(f"[{commit_display}]({commit_url})")
        else:
            parts.append(commit_display)
    if not parts:
        return ""
    return "(" + ", ".join(parts) + ")"


__all__ = ["render_markdown"]
