"""Grouping and ordering helpers for changelog sections."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import ChangeItem, ChangelogSection

SECTION_TITLES: Dict[str, str] = {
    "breaking": "Breaking Changes",
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "docs": "Documentation",
    "refactor": "Refactoring",
    "test": "Tests",
    "build": "Build",
    "ci": "Continuous Integration",
    "style": "Style",
    "chore": "Chores",
    "revert": "Reverted",
    "security": "Security",
    "other": "Other",
}

SECTION_ALIASES: Dict[str, str] = {
    "feature": "feat",
    "bugfix": "fix",
    "hotfix": "fix",
    "performance": "perf",
    "documentation": "docs",
    "tests": "test",
    "ci": "ci",
    "dependencies": "chore",
    "deps": "chore",
    "dependabot": "chore",
    "security": "security",
}

DEFAULT_ORDER: Sequence[str] = (
    "breaking",
    "feat",
    "fix",
    "perf",
    "docs",
    "refactor",
    "test",
    "build",
    "ci",
    "style",
    "security",
    "chore",
    "revert",
)


def group_items(
    items: Iterable[ChangeItem],
    *,
    order: Sequence[str] | None = None,
    dedupe_by: Optional[str] = None,
    sort_items: bool = True,
    include_empty: bool = False,
    sort_key: Optional[Callable[[ChangeItem], Tuple]] = None,
) -> List[ChangelogSection]:
    """Group change items into sections with stable ordering.

    Parameters
    ----------
    items:
        Iterable of change items to group.
    order:
        Optional custom sequence controlling section ordering. Defaults to
        :data:`DEFAULT_ORDER` with a trailing "other" bucket if needed.
    dedupe_by:
        Optional metadata key used to collapse duplicate changes (e.g., PR number).
    sort_items:
        Sort change items within each section using ``sort_key`` or a default
        alphabetical sort.
    include_empty:
        When True, produce empty sections for all keys in ``order``.
    sort_key:
        Custom callable producing a sort key for a change item.
    """

    order_sequence = list(order or DEFAULT_ORDER)
    groups: Dict[str, List[ChangeItem]] = defaultdict(list)

    seen_keys = set()
    for item in items:
        if dedupe_by:
            dedupe_value = None
            if item.metadata:
                dedupe_value = item.metadata.get(dedupe_by)
            if not dedupe_value and item.references:
                dedupe_value = item.references.get(dedupe_by)
            if dedupe_value:
                if dedupe_value in seen_keys:
                    continue
                seen_keys.add(dedupe_value)
        section_key = resolve_section_key(item)
        groups[section_key].append(item)

    sections: List[ChangelogSection] = []
    sort_key = sort_key or _default_sort_key
    for key in order_sequence:
        section_items = groups.pop(key, [])
        if not section_items and not include_empty:
            continue
        if sort_items:
            section_items.sort(key=sort_key)
        sections.append(ChangelogSection(title=_section_title(key), items=section_items))

    if groups:
        remaining_items: List[ChangeItem] = []
        for key in sorted(groups.keys()):
            bucket = groups[key]
            if sort_items:
                bucket.sort(key=sort_key)
            remaining_items.extend(bucket)
        sections.append(ChangelogSection(title=_section_title("other"), items=remaining_items))

    return sections


def resolve_section_key(item: ChangeItem) -> str:
    """Resolve the canonical section key for a change item."""

    if item.breaking:
        return "breaking"
    if not item.type:
        return "other"
    normalized = item.type.lower()
    canonical = SECTION_ALIASES.get(normalized, normalized)
    return canonical if canonical in SECTION_TITLES else "other"


def _section_title(key: str) -> str:
    return SECTION_TITLES.get(key, key.title())


def _default_sort_key(item: ChangeItem) -> Tuple:
    rank = item.metadata.get("sort_order") if item.metadata else None
    return (
        rank if isinstance(rank, int) else 0,
        item.title.lower(),
    )


__all__ = [
    "DEFAULT_ORDER",
    "SECTION_ALIASES",
    "SECTION_TITLES",
    "group_items",
    "resolve_section_key",
]
