"""High-level changelog assembly logic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .grouper import DEFAULT_ORDER, group_items
from .models import ChangeItem, Changelog, CommitInfo, PullRequestInfo
from .parser import ParsedCommitMessage, classify_change_type, parse_commit_message
from .summarizer import BaseSummarizer, SummaryRequest

MAX_SUMMARY_BODY_CHARS = 1600


def filter_commits(
    commits: Sequence[CommitInfo],
    *,
    include_types: Optional[Sequence[str]] = None,
    exclude_scopes: Optional[Sequence[str]] = None,
    author_filter: Optional[str] = None,
    include_paths: Optional[Sequence[str]] = None,
    exclude_paths: Optional[Sequence[str]] = None,
) -> List[CommitInfo]:
    """Filter commits based on type, scope, and author criteria.

    Args:
        commits: Sequence of commits to filter.
        include_types: If provided, only include commits with these types (e.g., ["feat", "fix"]).
        exclude_scopes: If provided, exclude commits with these scopes (e.g., ["deps", "ci"]).
        author_filter: Regex pattern to match against author name or email.

    Returns:
        Filtered list of commits.
    """
    result: List[CommitInfo] = []
    author_pattern = re.compile(author_filter, re.IGNORECASE) if author_filter else None
    include_path_patterns = _prepare_path_patterns(include_paths)
    exclude_path_patterns = _prepare_path_patterns(exclude_paths)

    for commit in commits:
        # Parse commit to extract type and scope
        parsed = parse_commit_message(commit.message)
        commit_type = parsed.type or classify_change_type(commit.message)
        commit_scope = parsed.scope

        # Filter by include_types
        if include_types:
            if commit_type not in include_types:
                continue

        # Filter by exclude_scopes
        if exclude_scopes and commit_scope:
            if commit_scope in exclude_scopes:
                continue

        # Filter by author_filter regex
        if author_pattern:
            name_match = author_pattern.search(commit.author_name or "")
            email_match = author_pattern.search(commit.author_email or "")
            if not (name_match or email_match):
                continue

        # Filter by include_paths
        if include_path_patterns:
            if not _paths_match_patterns(commit.files, include_path_patterns):
                continue

        # Filter by exclude_paths
        if exclude_path_patterns and commit.files:
            if _paths_match_patterns(commit.files, exclude_path_patterns):
                continue

        result.append(commit)

    return result


@dataclass
class CommitEntry:
    commit: CommitInfo
    parsed: ParsedCommitMessage
    change_type: str
    type_source: str


@dataclass
class ChangeBucket:
    identifier: str
    commits: List[CommitEntry] = field(default_factory=list)
    pull_request: Optional[PullRequestInfo] = None

    @property
    def primary(self) -> CommitEntry:
        return self.commits[0]


class ChangelogBuilder:
    """Construct changelog data structures from commits and pull requests."""

    def __init__(
        self,
        *,
        summarizer: Optional[BaseSummarizer] = None,
        section_order: Sequence[str] | None = None,
        dedupe_prs: bool = True,
        include_scopes: bool = True,
        summary_body_limit: int = MAX_SUMMARY_BODY_CHARS,
    ) -> None:
        self.summarizer = summarizer
        self.section_order = section_order or DEFAULT_ORDER
        self.dedupe_prs = dedupe_prs
        self.include_scopes = include_scopes
        self.summary_body_limit = summary_body_limit

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(
        self,
        *,
        version: Optional[str],
        release_date: Optional[datetime],
        commits: Sequence[CommitInfo],
        commit_prs: Optional[Dict[str, List[PullRequestInfo]]] = None,
        pr_index: Optional[Dict[int, PullRequestInfo]] = None,
    ) -> Changelog:
        commit_prs = commit_prs or {}
        pr_index = pr_index or {}
        buckets = self._build_buckets(commits, commit_prs, pr_index)
        summary_map = self._generate_summaries(buckets)
        change_items = [
            self._bucket_to_change_item(bucket, summary_map.get(bucket.identifier))
            for bucket in buckets
        ]
        dedupe_key = "pr_number" if self.dedupe_prs else None
        sections = group_items(change_items, order=self.section_order, dedupe_by=dedupe_key)
        return Changelog(version=version, date=release_date, sections=sections)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_buckets(
        self,
        commits: Sequence[CommitInfo],
        commit_prs: Dict[str, List[PullRequestInfo]],
        pr_index: Dict[int, PullRequestInfo],
    ) -> List[ChangeBucket]:
        buckets: List[ChangeBucket] = []
        bucket_index: Dict[str, ChangeBucket] = {}
        for commit in commits:
            parsed = parse_commit_message(commit.message)
            change_type, type_source = self._determine_change_type(parsed, commit)
            entry = CommitEntry(
                commit=commit, parsed=parsed, change_type=change_type, type_source=type_source
            )
            pull_request = self._resolve_pull_request(commit, commit_prs, pr_index)
            identifier = self._bucket_identifier(entry, pull_request)
            bucket = bucket_index.get(identifier)
            if bucket is None:
                bucket = ChangeBucket(identifier=identifier, pull_request=pull_request)
                bucket_index[identifier] = bucket
                buckets.append(bucket)
            if pull_request and bucket.pull_request is None:
                bucket.pull_request = pull_request
            bucket.commits.append(entry)
        return buckets

    def _generate_summaries(self, buckets: Sequence[ChangeBucket]) -> Dict[str, str]:
        if not self.summarizer:
            return {}
        requests: List[SummaryRequest] = []
        for bucket in buckets:
            requests.append(self._build_summary_request(bucket))
        results_map: Dict[str, str] = {}
        for result in self.summarizer.summarize(requests):
            results_map[result.identifier] = result.summary
        return results_map

    def _bucket_to_change_item(self, bucket: ChangeBucket, summary: Optional[str]) -> ChangeItem:
        primary = bucket.primary
        fallback_title = self._default_title(bucket)
        title = summary or fallback_title
        scope = primary.parsed.scope if (self.include_scopes and primary.parsed.scope) else None
        breaking, breaking_notes = self._detect_breaking(bucket)
        references: Dict[str, str] = {}
        metadata: Dict[str, object] = {
            "commit_shas": [entry.commit.sha for entry in bucket.commits],
            "authors": sorted(
                {entry.commit.author_name for entry in bucket.commits if entry.commit.author_name}
            ),
            "type_source": primary.type_source,
        }
        if bucket.pull_request:
            references["pr"] = bucket.pull_request.url
            metadata["pr_number"] = str(bucket.pull_request.number)
            if bucket.pull_request.author:
                metadata.setdefault("authors", []).append(bucket.pull_request.author)
        references["commit"] = primary.commit.sha
        metadata["commit_count"] = len(bucket.commits)
        metadata.setdefault("type", primary.change_type)
        return ChangeItem(
            title=title,
            type=primary.change_type,
            scope=scope,
            breaking=breaking,
            summary=fallback_title,
            details=self._details(bucket),
            notes=breaking_notes,
            references=references,
            metadata={
                key: _unique_list(value) if isinstance(value, list) else value
                for key, value in metadata.items()
            },
        )

    def _default_title(self, bucket: ChangeBucket) -> str:
        if bucket.pull_request and bucket.pull_request.title:
            return bucket.pull_request.title
        parsed_subject = bucket.primary.parsed.subject.strip()
        return parsed_subject or bucket.primary.commit.subject

    def _details(self, bucket: ChangeBucket) -> Optional[str]:
        parts: List[str] = []
        if bucket.pull_request and bucket.pull_request.body:
            parts.append(bucket.pull_request.body.strip())
        for entry in bucket.commits:
            body = entry.parsed.body
            if body:
                parts.append(body)
        if not parts:
            return None
        combined = "\n\n".join(parts)
        return _truncate(combined, 4000)

    def _detect_breaking(self, bucket: ChangeBucket) -> Tuple[bool, List[str]]:
        notes: List[str] = []
        breaking = False
        for entry in bucket.commits:
            if entry.parsed.breaking:
                breaking = True
                notes.extend(entry.parsed.breaking_descriptions)
        if bucket.pull_request:
            labels = {label.lower() for label in bucket.pull_request.labels}
            if "breaking-change" in labels or "breaking" in labels:
                breaking = True
        return breaking, notes

    def _resolve_pull_request(
        self,
        commit: CommitInfo,
        commit_prs: Dict[str, List[PullRequestInfo]],
        pr_index: Dict[int, PullRequestInfo],
    ) -> Optional[PullRequestInfo]:
        if commit.pr_number and commit.pr_number in pr_index:
            return pr_index[commit.pr_number]
        direct = commit_prs.get(commit.sha) or []
        if direct:
            pr = direct[0]
            pr_index.setdefault(pr.number, pr)
            return pr
        return None

    def _determine_change_type(self, parsed: ParsedCommitMessage, commit: CommitInfo) -> Tuple[str, str]:
        if parsed.type:
            return parsed.type, "conventional"
        inferred = classify_change_type(commit.message)
        return inferred, "heuristic"

    def _build_summary_request(self, bucket: ChangeBucket) -> SummaryRequest:
        title = self._default_title(bucket)
        body_parts: List[str] = []
        diff_parts: List[str] = []
        
        if bucket.pull_request and bucket.pull_request.body:
            body_parts.append(bucket.pull_request.body.strip())
        for entry in bucket.commits:
            body = entry.parsed.body
            if body:
                body_parts.append(body)
            if entry.commit.diff:
                diff_parts.append(f"Diff for {entry.commit.short_sha()}:\n{entry.commit.diff}")
                
        body_text = "\n\n".join(body_parts)
        body_text = _truncate(body_text, self.summary_body_limit)
        
        diff_text = "\n\n".join(diff_parts)
        # Truncate total diff text to avoid massive context
        diff_text = _truncate(diff_text, 4000)
        
        return SummaryRequest(
            identifier=bucket.identifier, 
            title=title, 
            body=body_text or None,
            diff=diff_text or None
        )

    def _bucket_identifier(
        self, entry: CommitEntry, pull_request: Optional[PullRequestInfo]
    ) -> str:
        if pull_request:
            return f"pr-{pull_request.number}"
        return f"commit-{entry.commit.sha}"


def _truncate(value: str, limit: int) -> str:
    if limit <= 0 or len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _unique_list(values: List[str]) -> List[str]:
    seen = set()
    unique: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _prepare_path_patterns(patterns: Optional[Sequence[str]]) -> List[str]:
    if not patterns:
        return []
    normalized = []
    for pattern in patterns:
        if not pattern:
            continue
        normalized.append(_normalize_path(pattern))
    return normalized


def _paths_match_patterns(paths: Iterable[str], patterns: Sequence[str]) -> bool:
    for path in paths:
        normalized_path = _normalize_path(path)
        for pattern in patterns:
            if _path_matches(normalized_path, pattern):
                return True
    return False


def _path_matches(path: str, pattern: str) -> bool:
    if not pattern:
        return False
    if any(char in pattern for char in "*?[]"):
        return fnmatch(path, pattern)
    if path == pattern:
        return True
    return path.startswith(pattern + "/")


def _normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/").lstrip("./")
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


__all__ = ["ChangeBucket", "ChangelogBuilder", "CommitEntry", "filter_commits"]
