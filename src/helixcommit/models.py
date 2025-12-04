"""Dataclasses representing commits, pull requests, and changelog structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class CommitInfo:
    """Normalized representation of a Git commit."""

    sha: str
    subject: str
    body: str
    author_name: str
    author_email: str
    authored_date: datetime
    committed_date: datetime
    is_merge: bool = False
    pr_number: Optional[int] = None
    labels: List[str] = field(default_factory=list)
    diff: Optional[str] = None
    files: List[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        """Return the full commit message (subject + body)."""
        if self.body:
            return f"{self.subject}\n\n{self.body}".strip()
        return self.subject

    def short_sha(self, length: int = 7) -> str:
        """Return the short SHA for display purposes."""
        return self.sha[:length]


@dataclass
class PullRequestInfo:
    """Metadata about an associated GitHub pull request."""

    number: int
    title: str
    url: str
    author: Optional[str]
    merged_at: Optional[datetime]
    body: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    assignees: List[str] = field(default_factory=list)


@dataclass
class ChangeItem:
    """A single change entry destined for a changelog section."""

    title: str
    type: str
    scope: Optional[str]
    breaking: bool
    summary: Optional[str] = None
    details: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    references: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangelogSection:
    """Collection of related change items."""

    title: str
    items: List[ChangeItem] = field(default_factory=list)

    def extend(self, changes: Iterable[ChangeItem]) -> None:
        """Append multiple change items to the section."""
        self.items.extend(changes)


@dataclass
class Changelog:
    """Top-level changelog container."""

    version: Optional[str]
    date: Optional[datetime]
    sections: List[ChangelogSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ChangeItem",
    "Changelog",
    "ChangelogSection",
    "CommitInfo",
    "PullRequestInfo",
]
