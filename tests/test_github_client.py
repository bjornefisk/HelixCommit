import os
import time

import pytest
import requests
import responses

import helixcommit.github_client as gh_client_module
from helixcommit.github_client import GitHubClient, GitHubSettings


@responses.activate
def test_get_pull_request_parses_response():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/42",
        json={
            "number": 42,
            "title": "Add payments endpoint",
            "html_url": "https://github.com/example/project/pull/42",
            "merged_at": "2024-05-01T12:34:56Z",
            "user": {"login": "octocat"},
            "labels": [{"name": "feature"}],
            "assignees": [{"login": "reviewer"}],
            "body": "Implements the new payments endpoint.",
        },
        status=200,
    )

    client = GitHubClient(GitHubSettings(owner="example", repo="project", token="test-token"))
    pull = client.get_pull_request(42)
    client.close()

    assert pull is not None
    assert pull.number == 42
    assert pull.title == "Add payments endpoint"
    assert pull.author == "octocat"
    assert pull.labels == ["feature"]


@responses.activate
def test_find_pull_requests_by_commit_handles_missing():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/commits/abc123/pulls",
        json=[],
        status=200,
        match=[
            responses.matchers.header_matcher(
                {"Accept": "application/vnd.github.groot-preview+json"}
            )
        ],
    )

    client = GitHubClient(GitHubSettings(owner="example", repo="project"))
    pulls = client.find_pull_requests_by_commit("abc123")
    client.close()

    assert pulls == []


@responses.activate
def test_get_pull_request_retries_on_5xx(monkeypatch):
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/99",
        json={"message": "upstream error"},
        status=500,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/99",
        json={
            "number": 99,
            "title": "Stabilize feature flag",
            "html_url": "https://github.com/example/project/pull/99",
        },
        status=200,
    )
    monkeypatch.setattr(gh_client_module.random, "random", lambda: 0.5)
    sleep_calls: list[float] = []

    def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    client = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        max_retries=2,
        backoff_base=0.1,
        backoff_cap=0.1,
        sleep_func=fake_sleep,
    )
    pull = client.get_pull_request(99)
    client.close()

    assert pull is not None
    assert pull.number == 99
    assert len(responses.calls) == 2
    assert pytest.approx(sleep_calls, rel=1e-6) == [0.05]


@responses.activate
def test_get_pull_request_retries_on_timeout(monkeypatch):
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/7",
        body=requests.exceptions.Timeout("timeout"),
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/7",
        json={
            "number": 7,
            "title": "Handle network hiccups",
            "html_url": "https://github.com/example/project/pull/7",
        },
        status=200,
    )
    monkeypatch.setattr(gh_client_module.random, "random", lambda: 0.25)
    sleep_calls: list[float] = []

    def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    client = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        max_retries=2,
        backoff_base=0.2,
        backoff_cap=0.2,
        sleep_func=fake_sleep,
    )
    pull = client.get_pull_request(7)
    client.close()

    assert pull is not None
    assert pull.number == 7
    assert len(responses.calls) == 2
    assert pytest.approx(sleep_calls, rel=1e-6) == [0.05]


@responses.activate
def test_get_pull_request_respects_retry_after(monkeypatch):
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/101",
        json={"message": "rate limited"},
        status=429,
        headers={"Retry-After": "1"},
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/101",
        json={
            "number": 101,
            "title": "Reduce API calls",
            "html_url": "https://github.com/example/project/pull/101",
        },
        status=200,
    )
    sleep_calls: list[float] = []

    def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    client = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        max_retries=2,
        sleep_func=fake_sleep,
    )
    pull = client.get_pull_request(101)
    client.close()

    assert pull is not None
    assert pull.number == 101
    assert len(responses.calls) == 2
    assert pytest.approx(sleep_calls, rel=1e-6) == [1.0]


@responses.activate
def test_get_pull_request_handles_rate_limit_reset(monkeypatch):
    fixed_now = 1_700_000_000.0
    monkeypatch.setattr(gh_client_module.time, "time", lambda: fixed_now)
    monkeypatch.setattr(gh_client_module.random, "random", lambda: 0.5)
    reset_at = int(fixed_now) + 3
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/55",
        json={"message": "rate limited"},
        status=403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset_at)},
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/55",
        json={
            "number": 55,
            "title": "Respect rate limits",
            "html_url": "https://github.com/example/project/pull/55",
        },
        status=200,
    )
    sleep_calls: list[float] = []

    def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    client = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        max_retries=2,
        sleep_func=fake_sleep,
    )
    pull = client.get_pull_request(55)
    client.close()

    assert pull is not None
    assert pull.number == 55
    assert len(responses.calls) == 2
    assert pytest.approx(sleep_calls, rel=1e-6) == [3.0]


@responses.activate
def test_disk_cache_serves_pr_from_disk(tmp_path, monkeypatch):
    cache_dir = tmp_path / "gh-cache"
    responses.add(
        responses.GET,
        "https://api.github.com/repos/example/project/pulls/5",
        json={
            "number": 5,
            "title": "Cache me if you can",
            "html_url": "https://github.com/example/project/pull/5",
        },
        status=200,
    )
    client = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        enable_disk_cache=True,
        cache_dir=cache_dir,
        cache_ttl_seconds=600,
    )
    pull = client.get_pull_request(5)
    client.close()

    assert pull is not None
    assert pull.title == "Cache me if you can"
    assert len(responses.calls) == 1

    # Second client should hit the disk cache; no HTTP stubs remaining.
    client_cached = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        enable_disk_cache=True,
        cache_dir=cache_dir,
        cache_ttl_seconds=600,
    )
    pull_cached = client_cached.get_pull_request(5)
    client_cached.close()

    assert pull_cached is not None
    assert pull_cached.title == "Cache me if you can"
    assert len(responses.calls) == 1


@responses.activate
def test_disk_cache_expires_after_ttl(tmp_path, monkeypatch):
    cache_dir = tmp_path / "gh-cache-expiring"
    url = "https://api.github.com/repos/example/project/pulls/88"
    responses.add(
        responses.GET,
        url,
        json={
            "number": 88,
            "title": "Initial title",
            "html_url": "https://github.com/example/project/pull/88",
        },
        status=200,
    )
    client = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        enable_disk_cache=True,
        cache_dir=cache_dir,
        cache_ttl_seconds=1,
    )
    first = client.get_pull_request(88)
    client.close()

    assert first is not None
    assert first.title == "Initial title"

    cache_file = cache_dir / "pr" / "example" / "project" / "88.json"
    assert cache_file.exists()
    stale_time = time.time() - 120
    os.utime(cache_file, (stale_time, stale_time))

    responses.add(
        responses.GET,
        url,
        json={
            "number": 88,
            "title": "Refreshed title",
            "html_url": "https://github.com/example/project/pull/88",
        },
        status=200,
    )
    client_refresh = GitHubClient(
        GitHubSettings(owner="example", repo="project"),
        enable_disk_cache=True,
        cache_dir=cache_dir,
        cache_ttl_seconds=1,
    )
    refreshed = client_refresh.get_pull_request(88)
    client_refresh.close()

    assert refreshed is not None
    assert refreshed.title == "Refreshed title"
    # Two HTTP calls in total for this endpoint (initial + refresh).
    assert sum(1 for call in responses.calls if call.request.url == url) == 2
