"""GitHub API client helpers."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from dateutil.parser import isoparse

from .cache import DiskCache
from .models import PullRequestInfo

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 0.5
DEFAULT_BACKOFF_CAP = 8.0
DEFAULT_CACHE_TTL_SECONDS = 600
DEFAULT_CACHE_DIR = Path(".helixcommit-cache/github")
CACHE_VALUE_KEY = "__cache_value__"

CACHE_ENABLED_ENV = "HELIXCOMMIT_GH_CACHE"
CACHE_DIR_ENV = "HELIXCOMMIT_GH_CACHE_DIR"
CACHE_TTL_MINUTES_ENV = "HELIXCOMMIT_GH_CACHE_TTL_MINUTES"
CACHE_TTL_SECONDS_ENV = "HELIXCOMMIT_GH_CACHE_TTL_SECONDS"
RETRY_MAX_ENV = "HELIXCOMMIT_GH_MAX_RETRIES"
RETRY_BASE_ENV = "HELIXCOMMIT_GH_BACKOFF_BASE_SEC"
RETRY_CAP_ENV = "HELIXCOMMIT_GH_BACKOFF_CAP_SEC"


def _env_flag(name: str) -> Optional[bool]:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _resolve_cache_ttl_seconds() -> int:
    ttl_seconds = _env_int(CACHE_TTL_SECONDS_ENV, -1)
    if ttl_seconds >= 0:
        return ttl_seconds
    ttl_minutes = _env_int(CACHE_TTL_MINUTES_ENV, -1)
    if ttl_minutes >= 0:
        return ttl_minutes * 60
    return DEFAULT_CACHE_TTL_SECONDS


def _unwrap_cache_value(data: Any) -> Any:
    if isinstance(data, dict) and CACHE_VALUE_KEY in data:
        return data[CACHE_VALUE_KEY]
    return data


def _wrap_cache_value(value: Any) -> Dict[str, Any]:
    return {CACHE_VALUE_KEY: value}


def _parse_retry_after(value: str) -> Optional[float]:
    try:
        seconds = float(value)
        return max(0.0, seconds)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = (parsed - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)


def _retry_after_seconds(response: requests.Response) -> Optional[float]:
    header = response.headers.get("Retry-After")
    if not header:
        return None
    return _parse_retry_after(header)


def _rate_limit_reset_delay(response: requests.Response) -> Optional[float]:
    reset_header = response.headers.get("X-RateLimit-Reset")
    if not reset_header:
        return None
    try:
        reset_epoch = int(reset_header)
    except ValueError:
        return None
    delay = reset_epoch - int(time.time())
    return max(0.0, float(delay))


class GitHubApiError(RuntimeError):
    """Raised when the GitHub API responds with an error."""

    def __init__(self, method: str, url: str, status_code: int, message: str | None = None) -> None:
        text = message or ""
        super().__init__(f"GitHub API {status_code} for {method} {url}: {text}")
        self.method = method
        self.url = url
        self.status_code = status_code
        self.message = text


class GitHubRateLimitError(GitHubApiError):
    """Raised when the GitHub API rate limit is exceeded."""

    def __init__(self, method: str, url: str, reset_at: Optional[int]) -> None:
        message = "Rate limit exceeded"
        if reset_at:
            message = f"{message}; resets at {reset_at}"
        super().__init__(method, url, 429, message)
        self.reset_at = reset_at


@dataclass(slots=True)
class GitHubSettings:
    owner: str
    repo: str
    token: Optional[str] = None
    api_url: str = DEFAULT_API_URL


class GitHubClient:
    """Simple wrapper around the GitHub REST API."""

    def __init__(
        self,
        settings: GitHubSettings,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
        backoff_cap: Optional[float] = None,
        enable_disk_cache: Optional[bool] = None,
        cache_dir: Optional[str | Path] = None,
        cache_ttl_seconds: Optional[int] = None,
        sleep_func: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.settings = settings
        self.timeout = timeout
        env_retries = _env_int(RETRY_MAX_ENV, DEFAULT_MAX_RETRIES)
        self._max_retries = max(0, max_retries if max_retries is not None else env_retries)
        env_backoff_base = _env_float(RETRY_BASE_ENV, DEFAULT_BACKOFF_BASE)
        env_backoff_cap = _env_float(RETRY_CAP_ENV, DEFAULT_BACKOFF_CAP)
        self._backoff_base = backoff_base if backoff_base is not None else env_backoff_base
        self._backoff_cap = backoff_cap if backoff_cap is not None else env_backoff_cap
        self._backoff_base = max(0.0, self._backoff_base)
        self._backoff_cap = max(0.0, self._backoff_cap)
        if self._backoff_cap > 0 and self._backoff_base > self._backoff_cap:
            self._backoff_cap = self._backoff_base
        self._sleep = sleep_func or time.sleep
        cache_flag = enable_disk_cache
        if cache_flag is None:
            env_flag = _env_flag(CACHE_ENABLED_ENV)
            cache_flag = env_flag if env_flag is not None else False
        ttl_seconds = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else _resolve_cache_ttl_seconds()
        )
        ttl_seconds = max(0, ttl_seconds)
        base_cache_dir: Optional[Path] = None
        if cache_flag:
            cache_dir_env = os.getenv(CACHE_DIR_ENV)
            cache_dir_value = cache_dir if cache_dir is not None else cache_dir_env
            base_cache_dir = Path(cache_dir_value) if cache_dir_value else DEFAULT_CACHE_DIR
            base_cache_dir = base_cache_dir.expanduser()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "HelixCommit/0.1.0",
            }
        )
        if settings.token:
            self._session.headers["Authorization"] = f"Bearer {settings.token}"
        self._base_url = settings.api_url.rstrip("/")
        self._pr_cache: Dict[int, PullRequestInfo] = {}
        self._commit_cache: Dict[str, List[PullRequestInfo]] = {}
        self._disk_cache: Optional[DiskCache] = None
        if cache_flag and ttl_seconds > 0 and base_cache_dir is not None:
            self._disk_cache = DiskCache(base_cache_dir, ttl_seconds=ttl_seconds)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "GitHubClient":  # pragma: no cover - context manager sugar
        return self

    def __exit__(self, *exc_info: object) -> None:  # pragma: no cover - context manager sugar
        self.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_pull_request(self, number: int) -> Optional[PullRequestInfo]:
        if number in self._pr_cache:
            return self._pr_cache[number]
        if self._disk_cache:
            cached = self._disk_cache.get(self._cache_key_for_pull(number))
            if cached is not None:
                payload = _unwrap_cache_value(cached)
                if payload is None:
                    return None
                pr_info = self._to_pr_info(payload)
                self._pr_cache[number] = pr_info
                return pr_info
        path = f"/repos/{self.settings.owner}/{self.settings.repo}/pulls/{number}"
        response = self._request("GET", path, allow_statuses=(404,))
        if response.status_code == 404:
            if self._disk_cache:
                self._disk_cache.set(self._cache_key_for_pull(number), _wrap_cache_value(None))
            return None
        data = response.json()
        if self._disk_cache:
            self._disk_cache.set(self._cache_key_for_pull(number), _wrap_cache_value(data))
        pr_info = self._to_pr_info(data)
        self._pr_cache[number] = pr_info
        return pr_info

    def find_pull_requests_by_commit(self, sha: str) -> List[PullRequestInfo]:
        if sha in self._commit_cache:
            return self._commit_cache[sha]
        if self._disk_cache:
            cached = self._disk_cache.get(self._cache_key_for_commit(sha))
            if cached is not None:
                payload = _unwrap_cache_value(cached)
                if payload is None:
                    self._commit_cache[sha] = []
                    return []
                pull_requests = [self._to_pr_info(item) for item in payload]
                self._commit_cache[sha] = pull_requests
                for pr in pull_requests:
                    self._pr_cache.setdefault(pr.number, pr)
                return pull_requests
        path = f"/repos/{self.settings.owner}/{self.settings.repo}/commits/{sha}/pulls"
        response = self._request(
            "GET",
            path,
            headers={"Accept": "application/vnd.github.groot-preview+json"},
            allow_statuses=(404,),
        )
        if response.status_code == 404:
            self._commit_cache[sha] = []
            if self._disk_cache:
                self._disk_cache.set(self._cache_key_for_commit(sha), _wrap_cache_value(None))
            return []
        items = response.json()
        if self._disk_cache:
            self._disk_cache.set(self._cache_key_for_commit(sha), _wrap_cache_value(items))
        pull_requests = [self._to_pr_info(item) for item in items]
        self._commit_cache[sha] = pull_requests
        for pr in pull_requests:
            self._pr_cache.setdefault(pr.number, pr)
        return pull_requests

    def batch_pull_requests(self, numbers: Sequence[int]) -> Dict[int, PullRequestInfo]:
        results: Dict[int, PullRequestInfo] = {}
        for number in numbers:
            pr = self.get_pull_request(number)
            if pr:
                results[number] = pr
        return results

    def map_commits_to_prs(self, shas: Iterable[str]) -> Dict[str, List[PullRequestInfo]]:
        mapping: Dict[str, List[PullRequestInfo]] = {}
        for sha in shas:
            mapping[sha] = self.find_pull_requests_by_commit(sha)
        return mapping

    def _cache_key_for_pull(self, number: int) -> str:
        return f"pr/{self.settings.owner}/{self.settings.repo}/{number}"

    def _cache_key_for_commit(self, sha: str) -> str:
        return f"commit_prs/{self.settings.owner}/{self.settings.repo}/{sha}"

    def _is_retryable_exception(self, exc: requests.RequestException) -> bool:
        return isinstance(exc, (requests.Timeout, requests.ConnectionError))

    def _compute_backoff(self, attempt: int) -> float:
        if self._backoff_base <= 0 or self._backoff_cap <= 0:
            return 0.0
        upper = min(self._backoff_cap, self._backoff_base * (2**attempt))
        if upper <= 0:
            return 0.0
        return random.random() * upper

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code >= 500 or status_code == 408

    def _is_rate_limit_response(self, response: requests.Response) -> bool:
        if response.status_code == 429:
            return True
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            return True
        return False

    def _rate_limit_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(self._backoff_cap, retry_after) if self._backoff_cap > 0 else retry_after
        reset_delay = _rate_limit_reset_delay(response)
        if reset_delay is not None:
            return min(self._backoff_cap, reset_delay) if self._backoff_cap > 0 else reset_delay
        return self._compute_backoff(attempt)

    def _build_rate_limit_error(
        self, method: str, url: str, response: requests.Response
    ) -> GitHubRateLimitError:
        reset_hdr = response.headers.get("X-RateLimit-Reset")
        reset_at = int(reset_hdr) if reset_hdr and reset_hdr.isdigit() else None
        return GitHubRateLimitError(method, url, reset_at)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        allow_statuses: Tuple[int, ...] = (),
    ) -> requests.Response:
        url = f"{self._base_url}{path}"
        merged_headers = dict(self._session.headers)
        if headers:
            merged_headers.update(headers)
        last_exception: Optional[requests.RequestException] = None
        last_response: Optional[requests.Response] = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    headers=merged_headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_exception = exc
                if not self._is_retryable_exception(exc) or attempt >= self._max_retries:
                    raise GitHubApiError(method, url, 0, str(exc)) from exc
                delay = self._compute_backoff(attempt)
                if delay > 0:
                    self._sleep(delay)
                continue

            last_response = response
            if response.status_code in allow_statuses or response.ok:
                return response

            if self._is_rate_limit_response(response):
                if attempt >= self._max_retries:
                    error = self._build_rate_limit_error(method, url, response)
                    response.close()
                    raise error
                delay = self._rate_limit_delay(response, attempt)
                response.close()
                if delay > 0:
                    self._sleep(delay)
                continue

            if self._is_retryable_status(response.status_code) and attempt < self._max_retries:
                delay = self._compute_backoff(attempt)
                response.close()
                if delay > 0:
                    self._sleep(delay)
                continue

            message = _extract_error_message(response)
            status_code = response.status_code
            response.close()
            raise GitHubApiError(method, url, status_code, message)

        if last_exception is not None:
            raise GitHubApiError(method, url, 0, str(last_exception)) from last_exception
        if last_response is not None:
            if self._is_rate_limit_response(last_response):
                error = self._build_rate_limit_error(method, url, last_response)
                last_response.close()
                raise error
            message = _extract_error_message(last_response)
            status_code = last_response.status_code
            last_response.close()
            raise GitHubApiError(method, url, status_code, message)
        raise GitHubApiError(method, url, 0, "Unknown GitHub API error")

    def _to_pr_info(self, data: Dict[str, object]) -> PullRequestInfo:
        number = int(data.get("number"))
        title = str(data.get("title") or "")
        url = str(data.get("html_url") or "")
        merged_at_raw = data.get("merged_at")
        merged_at = _parse_datetime(merged_at_raw)
        user = data.get("user") or {}
        author = user.get("login") if isinstance(user, dict) else None
        labels = _pluck_names(data.get("labels"))
        assignees = _pluck_names(data.get("assignees"))
        body = data.get("body") or None
        return PullRequestInfo(
            number=number,
            title=title,
            url=url,
            author=author,
            merged_at=merged_at,
            body=body,
            labels=labels,
            assignees=assignees,
        )


def _parse_datetime(value: object) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return isoparse(str(value))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _pluck_names(value: object) -> List[str]:
    names: List[str] = []
    if not isinstance(value, list):
        return names
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or item.get("login")
            if isinstance(name, str):
                names.append(name)
    return names


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str):
            return message
    return response.text


__all__ = [
    "GitHubApiError",
    "GitHubClient",
    "GitHubRateLimitError",
    "GitHubSettings",
]
