"""Utilities for reading Git commits using GitPython or subprocess."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence, Tuple

from dateutil import tz

from .models import CommitInfo

try:  # pragma: no cover - import fallback
    import git  # type: ignore[import]
except Exception:  # pragma: no cover
    git = None  # type: ignore[assignment]


UTC = tz.UTC


@dataclass(slots=True)
class CommitRange:
    """Describe the commit boundaries for iteration."""

    since: Optional[str] = None
    until: Optional[str] = None
    since_date: Optional[datetime] = None
    until_date: Optional[datetime] = None
    include_merges: bool = True
    max_count: Optional[int] = None
    paths: Sequence[str] = ()

    def rev_spec(self) -> str:
        """Return a revision spec usable by git."""
        since = self.since or ""
        until = self.until or ""
        if since and until:
            return f"{since}..{until}"
        if since:
            return f"{since}..HEAD"
        return until or "HEAD"


@dataclass(slots=True)
class TagInfo:
    """Lightweight description of a Git tag."""

    name: str
    sha: str
    tagged_date: Optional[datetime]
    message: Optional[str] = None
    is_annotated: bool = False


class GitRepository:
    """Wrapper around GitPython with a subprocess fallback."""

    def __init__(self, path: Path, *, prefer_gitpython: bool = True) -> None:
        self.path = path
        self._repo = None
        self._use_gitpython = False
        if prefer_gitpython and git is not None:
            try:
                self._repo = git.Repo(path)
            except Exception:  # pragma: no cover - fall back to CLI
                self._repo = None
        if self._repo is not None:
            self._use_gitpython = True
        else:
            self._ensure_git_cli_available()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def iter_commits(
        self,
        commit_range: CommitRange,
        *,
        include_diffs: bool = False,
        include_files: bool = False,
    ) -> Iterator[CommitInfo]:
        """Iterate over commits in the given range."""
        if self._use_gitpython:
            yield from self._iter_commits_gitpython(
                commit_range, include_diffs=include_diffs, include_files=include_files
            )
        else:
            yield from self._iter_commits_cli(
                commit_range, include_diffs=include_diffs, include_files=include_files
            )

    def get_commit_diff(self, sha: str, max_chars: int = 4000) -> str:
        """Fetch the diff for a specific commit, truncated to max_chars."""
        if self._use_gitpython and self._repo is not None:
            try:
                commit = self._repo.commit(sha)
                # Get diff against parent (or empty tree if root)
                parent = commit.parents[0] if commit.parents else None
                diffs = parent.diff(commit, create_patch=True) if parent else commit.diff(None, create_patch=True)
                
                full_diff = "\n".join(
                    (d.diff.tobytes().decode("utf-8", errors="replace") if isinstance(d.diff, memoryview)
                     else d.diff.decode("utf-8", errors="replace") if isinstance(d.diff, (bytes, bytearray))
                     else str(d.diff))
                    for d in diffs
                    if d.diff
                )
                return full_diff[:max_chars]
            except Exception:
                return ""
        
        # CLI fallback
        try:
            # git show --format= --patch <sha>
            output = self._run_git("show", "--format=", "--patch", sha)
            return output[:max_chars]
        except Exception:
            return ""

    def list_tags(self, pattern: Optional[str] = None) -> List[TagInfo]:
        """Return repository tags, newest first."""
        if self._use_gitpython:
            tags = self._list_tags_gitpython()
        else:
            tags = self._list_tags_cli()
        if pattern:
            regex = re.compile(pattern)
            tags = [tag for tag in tags if regex.search(tag.name)]
        # Sort by date (newest first), using index as secondary key to preserve chronological order
        # When dates are equal, higher index (newer tag) should come first
        indexed_tags = list(enumerate(tags))
        return [
            tag
            for _, tag in sorted(
                indexed_tags,
                key=lambda item: (item[1].tagged_date or datetime.min.replace(tzinfo=UTC), item[0]),
                reverse=True,
            )
        ]

    def get_tag(self, name: str) -> Optional[TagInfo]:
        """Return a single tag by name."""
        for tag in self.list_tags():
            if tag.name == name:
                return tag
        return None

    def resolve_default_branch(self) -> str:
        """Infer the repository's default branch, defaulting to main."""
        if self._use_gitpython and self._repo is not None:
            try:
                return self._repo.git.symbolic_ref("refs/remotes/origin/HEAD").split("/")[-1]
            except Exception:
                pass
        try:
            output = self._run_git("symbolic-ref", "refs/remotes/origin/HEAD")
            return output.strip().split("/")[-1]
        except Exception:
            return "main"

    def get_remote_url(self, remote: str = "origin") -> Optional[str]:
        """Fetch the URL for the given remote."""
        if self._use_gitpython and self._repo is not None:
            try:
                return self._repo.git.remote("get-url", remote).strip()
            except Exception:
                return None
        try:
            return self._run_git("remote", "get-url", remote).strip()
        except Exception:
            return None

    def get_github_slug(self, remote: str = "origin") -> Optional[Tuple[str, str]]:
        """Extract (owner, repo) from a GitHub remote URL."""
        url = self.get_remote_url(remote)
        if not url:
            return None
        match = re.search(
            r"(?:github\\.com[:/])(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\\.git)?$",
            url,
        )
        if not match:
            return None
        return match.group("owner"), match.group("repo")

    def get_gitlab_slug(self, remote: str = "origin") -> Optional[str]:
        """Extract project path from a GitLab remote URL.

        Supports gitlab.com and self-hosted GitLab instances.
        Returns the full project path (e.g., "group/subgroup/project").
        """
        url = self.get_remote_url(remote)
        if not url:
            return None
        # Match gitlab.com or common self-hosted GitLab patterns
        # SSH: git@gitlab.com:group/project.git
        # HTTPS: https://gitlab.com/group/project.git
        # Self-hosted: git@gitlab.example.com:group/project.git
        match = re.search(
            r"gitlab[^/:]*[:/](?P<path>.+?)(?:\.git)?$",
            url,
            re.IGNORECASE,
        )
        if not match:
            return None
        path = match.group("path")
        # Remove trailing .git if present (handles edge cases)
        if path.endswith(".git"):
            path = path[:-4]
        return path

    def get_bitbucket_slug(self, remote: str = "origin") -> Optional[Tuple[str, str]]:
        """Extract (workspace, repo_slug) from a Bitbucket remote URL.

        Supports bitbucket.org URLs.
        SSH: git@bitbucket.org:workspace/repo.git
        HTTPS: https://bitbucket.org/workspace/repo.git
        """
        url = self.get_remote_url(remote)
        if not url:
            return None
        match = re.search(
            r"bitbucket\.org[:/](?P<workspace>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$",
            url,
            re.IGNORECASE,
        )
        if not match:
            return None
        return match.group("workspace"), match.group("repo")

    def is_dirty(self) -> bool:
        """Check if the repository has uncommitted changes."""
        if self._use_gitpython and self._repo is not None:
            return self._repo.is_dirty(untracked_files=True)
        try:
            return bool(self._run_git("status", "--porcelain").strip())
        except Exception:
            return False

    def get_diff(self, staged: bool = False) -> str:
        """Get the diff of changes."""
        args = ["diff"]
        if staged:
            args.append("--cached")
        else:
            args.append("HEAD")

        if self._use_gitpython and self._repo is not None:
            return self._repo.git.diff(*args[1:])
        return self._run_git(*args)

    def stage_all(self) -> None:
        """Stage all changes."""
        if self._use_gitpython and self._repo is not None:
            self._repo.git.add(".")
        else:
            self._run_git("add", ".")

    def commit(self, message: str) -> None:
        """Create a commit with the given message."""
        if self._use_gitpython and self._repo is not None:
            self._repo.index.commit(message)
            return

        self._run_git("commit", "-m", message)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _iter_commits_gitpython(
        self,
        commit_range: CommitRange,
        *,
        include_diffs: bool = False,
        include_files: bool = False,
    ) -> Iterator[CommitInfo]:
        assert self._repo is not None  # for type checkers
        kwargs = {
            "rev": commit_range.rev_spec(),
            "max_count": commit_range.max_count,
            "paths": list(commit_range.paths) or None,
        }
        if commit_range.since_date:
            kwargs["since"] = commit_range.since_date.isoformat()
        if commit_range.until_date:
            kwargs["until"] = commit_range.until_date.isoformat()
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        for raw_commit in self._repo.iter_commits(**kwargs):
            if (
                not commit_range.include_merges
                and raw_commit.parents
                and len(raw_commit.parents) > 1
            ):
                continue
            message = raw_commit.message
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            elif isinstance(message, (bytearray, memoryview)):
                message = bytes(message).decode("utf-8", errors="replace")
            subject, body = self._split_message(message)
            authored_date = datetime.fromtimestamp(raw_commit.authored_date, tz=UTC)
            committed_date = datetime.fromtimestamp(raw_commit.committed_date, tz=UTC)
            
            diff = None
            if include_diffs:
                diff = self.get_commit_diff(raw_commit.hexsha)

            files: List[str] = []
            if include_files:
                files = self._get_commit_files_gitpython(raw_commit)

            yield CommitInfo(
                sha=raw_commit.hexsha,
                subject=subject,
                body=body,
                author_name=raw_commit.author.name or "",
                author_email=raw_commit.author.email or "",
                authored_date=authored_date,
                committed_date=committed_date,
                is_merge=len(raw_commit.parents) > 1,
                diff=diff,
                files=files,
            )

    def _iter_commits_cli(
        self,
        commit_range: CommitRange,
        *,
        include_diffs: bool = False,
        include_files: bool = False,
    ) -> Iterator[CommitInfo]:
        rev = commit_range.rev_spec()
        args = [
            "log",
            rev,
            "--pretty=format:%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%ct%x1f%s%x1f%b%x1e",
        ]
        if commit_range.max_count:
            args.extend(["-n", str(commit_range.max_count)])
        if commit_range.since_date:
            args.append(f"--since={commit_range.since_date.isoformat()}")
        if commit_range.until_date:
            args.append(f"--until={commit_range.until_date.isoformat()}")
        if commit_range.paths:
            args.append("--")
            args.extend(commit_range.paths)
        raw_output = self._run_git(*args)
        if not raw_output.strip():
            return
        for entry in raw_output.strip("\n\x1e").split("\x1e"):
            if not entry.strip():
                continue
            (
                sha,
                parents,
                author_name,
                author_email,
                author_ts,
                commit_ts,
                subject,
                body,
            ) = entry.split("\x1f")
            if not commit_range.include_merges and len(parents.split()) > 1:
                continue
            
            diff = None
            if include_diffs:
                diff = self.get_commit_diff(sha)

            files: List[str] = []
            if include_files:
                files = self._get_commit_files_cli(sha)

            yield CommitInfo(
                sha=sha,
                subject=subject.strip(),
                body=body.strip(),
                author_name=author_name.strip(),
                author_email=author_email.strip(),
                authored_date=datetime.fromtimestamp(int(author_ts), tz=UTC),
                committed_date=datetime.fromtimestamp(int(commit_ts), tz=UTC),
                is_merge=len(parents.split()) > 1,
                diff=diff,
                files=files,
            )

    def _get_commit_files_gitpython(self, raw_commit: Any) -> List[str]:
        try:
            stats = raw_commit.stats.files or {}
            return sorted(stats.keys())
        except Exception:
            return []

    def _get_commit_files_cli(self, sha: str) -> List[str]:
        try:
            output = self._run_git("show", "--pretty=format:", "--name-only", sha)
        except Exception:
            return []
        return [line.strip() for line in output.splitlines() if line.strip()]

    def _list_tags_gitpython(self) -> List[TagInfo]:
        assert self._repo is not None
        tags: List[TagInfo] = []
        for tag in self._repo.tags:
            tagged_date = None
            message = None
            is_annotated = False
            if tag.tag is not None:
                is_annotated = True
                tag_object = tag.tag
                if tag_object.tagged_date:
                    tagged_date = datetime.fromtimestamp(tag_object.tagged_date, tz=UTC)
                message = (tag_object.message or "").strip() or None
                sha = tag_object.object.hexsha
            else:
                # Lightweight tag pointing to a commit
                commit = tag.commit
                tagged_date = datetime.fromtimestamp(commit.committed_date, tz=UTC)
                sha = commit.hexsha
            tags.append(
                TagInfo(
                    name=tag.name,
                    sha=sha,
                    tagged_date=tagged_date,
                    message=message,
                    is_annotated=is_annotated,
                )
            )
        return tags

    def _list_tags_cli(self) -> List[TagInfo]:
        output = self._run_git(
            "for-each-ref",
            "--sort=-creatordate",
            "--format=%(refname:short)%00%(objectname)%00%(creatordate:iso8601)%00%(contents)",
            "refs/tags",
        )
        tags: List[TagInfo] = []
        for line in output.strip().splitlines():
            if not line:
                continue
            name, sha, date_str, message = line.split("\x00", 3)
            tagged_date: Optional[datetime]
            message = message.strip() or None
            if date_str:
                tagged_date = datetime.fromisoformat(date_str)
                if tagged_date.tzinfo is None:
                    tagged_date = tagged_date.replace(tzinfo=UTC)
            else:
                tagged_date = None
            tags.append(
                TagInfo(
                    name=name,
                    sha=sha,
                    tagged_date=tagged_date,
                    message=message,
                    is_annotated=bool(message),
                )
            )
        return tags

    def _split_message(self, message: str) -> Tuple[str, str]:
        if not message:
            return "", ""
        parts = message.split("\n", 1)
        subject = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else ""
        return subject, body

    def _run_git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.path,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout

    def _ensure_git_cli_available(self) -> None:
        try:
            self._run_git("rev-parse", "--is-inside-work-tree")
        except subprocess.CalledProcessError as exc:  # pragma: no cover - environment specific
            raise RuntimeError("Git repository not found or git CLI unavailable.") from exc


__all__ = ["CommitRange", "GitRepository", "TagInfo"]
