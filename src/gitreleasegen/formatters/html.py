"""HTML formatter for changelog output."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Iterable, List, Optional

from ..models import ChangeItem, Changelog


def render_html(changelog: Changelog) -> str:
    parts: List[str] = ['<section class="changelog">']
    parts.append(f"  <h2>{escape(_heading_text(changelog.version))}</h2>")
    if changelog.date:
        parts.append(
            f'  <p class="changelog-date">Released on {escape(_format_date(changelog.date))}</p>'
        )
    compare_url = changelog.metadata.get("compare_url") if changelog.metadata else None
    if compare_url:
        parts.append(
            f'  <p class="changelog-compare"><a href="{escape(compare_url)}">Compare changes</a></p>'
        )

    for section in changelog.sections:
        if not section.items:
            continue
        slug = _slugify(section.title)
        parts.append(f'  <section class="changelog-section changelog-section--{escape(slug)}">')
        parts.append(f"    <h3>{escape(section.title)}</h3>")
        parts.append('    <ul class="changelog-items">')
        for item in section.items:
            parts.append('      <li class="changelog-item">')
            parts.extend(_render_item(item))
            parts.append("      </li>")
        parts.append("    </ul>")
        parts.append("  </section>")
    parts.append("</section>")
    return "\n".join(parts)


def _render_item(item: ChangeItem) -> Iterable[str]:
    lines: List[str] = []
    scope_prefix = f"<strong>{escape(item.scope)}</strong> - " if item.scope else ""
    references = _format_references(item)
    title = escape(item.title)
    line = f'        <p class="changelog-item-title">{scope_prefix}{title}'
    if references:
        line += f' <span class="changelog-item-links">{references}</span>'
    line += "</p>"
    lines.append(line)
    if item.summary and item.summary != item.title:
        lines.append(
            f'        <p class="changelog-item-summary"><em>{escape(item.summary)}</em></p>'
        )
    for note in item.notes:
        lines.append(
            f'        <p class="changelog-item-note"><strong>BREAKING:</strong> {escape(note)}</p>'
        )
    if item.details:
        lines.append('        <div class="changelog-item-details">')
        for detail in item.details.splitlines():
            text = escape(detail)
            lines.append(f"          <p>{text}</p>" if text else "          <p></p>")
        lines.append("        </div>")
    return lines


def _heading_text(version: Optional[str]) -> str:
    return f"Release {version}" if version else "Release"


def _format_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _format_references(item: ChangeItem) -> str:
    links: List[str] = []
    pr_url = item.references.get("pr")
    pr_number = item.metadata.get("pr_number") if item.metadata else None
    if pr_url and pr_number:
        links.append(f'<a href="{escape(pr_url)}">#{escape(str(pr_number))}</a>')
    commit_ref = item.references.get("commit")
    if commit_ref:
        commit_display = escape(str(commit_ref)[:7])
        commit_url = item.references.get("commit_url")
        if commit_url and isinstance(commit_url, str) and commit_url.startswith("http"):
            links.append(f'<a href="{escape(commit_url)}">{commit_display}</a>')
        else:
            links.append(commit_display)
    return " ".join(links)


def _slugify(value: str) -> str:
    return "-".join(
        filter(None, "".join(ch.lower() if ch.isalnum() else " " for ch in value).split())
    )


__all__ = ["render_html"]
