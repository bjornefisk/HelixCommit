"""Plain text formatter for changelog output."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ..models import ChangeItem, Changelog


def render_text(changelog: Changelog) -> str:
    lines: List[str] = []
    lines.append(_heading(changelog.version))
    if changelog.date:
        lines.append(f"Released on {_format_date(changelog.date)}")
    compare_url = changelog.metadata.get("compare_url") if changelog.metadata else None
    if compare_url:
        lines.append(f"Compare: {compare_url}")
    lines.append("")

    for section in changelog.sections:
        if not section.items:
            continue
        lines.append(section.title.upper())
        for item in section.items:
            lines.extend(_render_item(item))
        lines.append("")

    return "\n".join(line for line in lines if line is not None).rstrip() + "\n"


def _heading(version: Optional[str]) -> str:
    return f"Release {version}" if version else "Release"


def _format_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _render_item(item: ChangeItem) -> List[str]:
    scope_prefix = f"[{item.scope}] " if item.scope else ""
    reference = _format_references(item)
    title_line = f"- {scope_prefix}{item.title}"
    if reference:
        title_line = f"{title_line} ({reference})"
    lines = [title_line]
    if item.summary and item.summary != item.title:
        lines.append(f"    {item.summary}")
    for note in item.notes:
        lines.append(f"    BREAKING: {note}")
    if item.details:
        for detail in item.details.splitlines():
            lines.append(f"    {detail}")
    return lines


def _format_references(item: ChangeItem) -> str:
    parts: List[str] = []
    pr_number = item.metadata.get("pr_number") if item.metadata else None
    pr_url = item.references.get("pr")
    if pr_number:
        parts.append(f"PR #{pr_number}")
        if pr_url:
            parts[-1] = f"{parts[-1]} {pr_url}"
    commit_ref = item.references.get("commit")
    if commit_ref:
        commit_display = str(commit_ref)[:7]
        commit_url = item.references.get("commit_url")
        if commit_url and isinstance(commit_url, str) and commit_url.startswith("http"):
            parts.append(f"Commit {commit_display} {commit_url}")
        else:
            parts.append(f"Commit {commit_display}")
    return "; ".join(parts)


__all__ = ["render_text"]
