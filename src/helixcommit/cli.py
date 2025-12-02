"""Command-line interface for HelixCommit."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import typer

from .changelog import ChangelogBuilder, filter_commits
from .commit_generator import CommitGenerator
from .config import load_config
from .formatters import html as html_formatter
from .formatters import json as json_formatter
from .formatters import markdown as markdown_formatter
from .formatters import text as text_formatter
from .formatters import yaml as yaml_formatter
from .template import TemplateEngine, detect_format_from_template
from .bitbucket_client import BitbucketClient, BitbucketSettings
from .git_client import CommitRange, GitRepository, TagInfo
from .github_client import GitHubClient, GitHubSettings
from .gitlab_client import GitLabClient, GitLabSettings
from .models import Changelog, CommitInfo, PullRequestInfo
from .summarizer import BaseSummarizer, PromptEngineeredSummarizer, SummaryRequest

APP_NAME = "HelixCommit"
DEFAULT_SUMMARY_CACHE = Path(".helixcommit-cache/summaries.json")
PR_NUMBER_PATTERN = re.compile(
    r"(?:\(#(?P<num_paren>\d+)\))|(?:pull request #(?P<num_pr>\d+))|(?:pr #(?P<num_alt>\d+))",
    re.IGNORECASE,
)
MERGE_PR_PATTERN = re.compile(r"merge pull request #(\d+)", re.IGNORECASE)
# GitLab MR patterns: (!123), merge request !123, MR !123
MR_NUMBER_PATTERN = re.compile(
    r"(?:\(!(?P<num_paren>\d+)\))|(?:merge request !(?P<num_mr>\d+))|(?:mr !(?P<num_alt>\d+))",
    re.IGNORECASE,
)
MERGE_MR_PATTERN = re.compile(r"merge branch .+ into .+", re.IGNORECASE)
# Bitbucket PR patterns: (pull request #123), PR #123, or merged in #123
BB_PR_NUMBER_PATTERN = re.compile(
    r"(?:pull request #(?P<num_pr>\d+))|(?:pr #(?P<num_alt>\d+))|(?:merged in .+#(?P<num_merged>\d+))",
    re.IGNORECASE,
)

# Environment variable names for API keys
API_KEY_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class MissingApiKeyError(Exception):
    """Raised when a required API key is not provided."""

    def __init__(self, provider: str, env_var: str) -> None:
        self.provider = provider
        self.env_var = env_var
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        return (
            f"Missing API key for '{self.provider}' provider.\n\n"
            f"To fix this, either:\n"
            f"  1. Set the {self.env_var} environment variable:\n"
            f"     export {self.env_var}='your-api-key'\n\n"
            f"  2. Pass it directly via the command line:\n"
            f"     --{self.provider.lower()}-api-key 'your-api-key'\n\n"
            f"  3. Add it to your config file (.helixcommit.toml or .helixcommit.yaml)"
        )


def _validate_api_key(
    provider: str,
    api_key: Optional[str],
) -> str:
    """Validate that an API key is provided for the given provider.

    Args:
        provider: The LLM provider name (openai, openrouter).
        api_key: The API key value (may be None).

    Returns:
        The API key if valid.

    Raises:
        MissingApiKeyError: If the API key is not provided.
    """
    if api_key:
        return api_key

    provider_lower = provider.lower()
    env_var = API_KEY_ENV_VARS.get(provider_lower, f"{provider_lower.upper()}_API_KEY")
    raise MissingApiKeyError(provider_lower, env_var)


# Pattern for relative date expressions like "2 weeks ago", "3 days ago"
RELATIVE_DATE_PATTERN = re.compile(
    r"^(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago$",
    re.IGNORECASE,
)


def _parse_date(value: str) -> datetime:
    """Parse a flexible date string into a timezone-aware datetime.

    Supports:
    - ISO 8601 dates (e.g., '2024-01-15', '2024-01-15T10:30:00')
    - Relative expressions (e.g., '2 weeks ago', '3 days ago', 'yesterday')
    - Natural language dates via dateutil.parser

    Args:
        value: The date string to parse.

    Returns:
        A timezone-aware datetime object (UTC).

    Raises:
        typer.BadParameter: If the date string cannot be parsed.
    """
    from dateutil import parser as date_parser
    from dateutil.relativedelta import relativedelta

    value = value.strip()

    # Handle special keywords
    if value.lower() == "yesterday":
        return datetime.now(timezone.utc) - relativedelta(days=1)
    if value.lower() == "today":
        return datetime.now(timezone.utc)

    # Handle relative expressions like "2 weeks ago"
    match = RELATIVE_DATE_PATTERN.match(value)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        # Map singular to plural for relativedelta kwargs
        unit_map = {
            "second": "seconds",
            "minute": "minutes",
            "hour": "hours",
            "day": "days",
            "week": "weeks",
            "month": "months",
            "year": "years",
        }
        kwargs = {unit_map[unit]: amount}
        return datetime.now(timezone.utc) - relativedelta(**kwargs)

    # Try parsing as ISO or natural date
    try:
        parsed = date_parser.parse(value)
        # Ensure timezone-aware (default to UTC if naive)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError) as e:
        raise typer.BadParameter(
            f"Cannot parse date '{value}'. Use ISO format (e.g., '2024-01-15') "
            f"or relative expressions (e.g., '2 weeks ago')."
        ) from e


def _typer_app() -> typer.Typer:
    return typer.Typer(help="Generate release notes from Git repositories.", no_args_is_help=True)


app = _typer_app()


class OutputFormat(str, Enum):
    markdown = "markdown"
    html = "html"
    text = "text"
    json = "json"
    yaml = "yaml"


class RagBackend(str, Enum):
    simple = "simple"
    chroma = "chroma"


@dataclass
class RangeContext:
    since_ref: Optional[str]
    until_ref: Optional[str]
    since_tag: Optional[TagInfo]
    until_tag: Optional[TagInfo]


@app.command()
def generate(
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="Repository path.",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to config file (.helixcommit.toml or .helixcommit.yaml).",
    ),
    since_tag: Optional[str] = typer.Option(None, help="Commits after this tag."),
    until_tag: Optional[str] = typer.Option(None, help="Commits up to this tag."),
    since: Optional[str] = typer.Option(None, help="Commits after this ref."),
    until: Optional[str] = typer.Option(None, help="Commits up to this ref."),
    since_date: Optional[str] = typer.Option(
        None, help="Commits after this date (ISO or relative, e.g., '2024-01-15', '2 weeks ago')."
    ),
    until_date: Optional[str] = typer.Option(
        None, help="Commits before this date (ISO or relative, e.g., '2024-06-01', 'yesterday')."
    ),
    unreleased: bool = typer.Option(False, help="HEAD vs latest tag."),
    output_format: Optional[OutputFormat] = typer.Option(
        None, "--format", case_sensitive=False, help="Output format (markdown/html/text/json)."
    ),
    out: Optional[Path] = typer.Option(None, help="Output file path."),
    use_llm: Optional[bool] = typer.Option(None, help="Use AI summaries."),
    llm_provider: Optional[str] = typer.Option(
        None, help="AI provider (openai/openrouter)."
    ),
    openai_model: Optional[str] = typer.Option(None, help="OpenAI model."),
    openai_api_key: Optional[str] = typer.Option(
        None, envvar="OPENAI_API_KEY", help="OpenAI API key."
    ),
    openrouter_model: Optional[str] = typer.Option(None, help="OpenRouter model."),
    openrouter_api_key: Optional[str] = typer.Option(
        None, envvar="OPENROUTER_API_KEY", help="OpenRouter API key."
    ),
    github_token: Optional[str] = typer.Option(
        None, envvar="GITHUB_TOKEN", help="GitHub API token."
    ),
    gitlab_token: Optional[str] = typer.Option(
        None, envvar="GITLAB_TOKEN", help="GitLab API token."
    ),
    bitbucket_token: Optional[str] = typer.Option(
        None, envvar="BITBUCKET_TOKEN", help="Bitbucket API token."
    ),
    include_scopes: Optional[bool] = typer.Option(
        None, "--include-scopes/--no-include-scopes", help="Show commit scopes."
    ),
    include_diffs: Optional[bool] = typer.Option(
        None, "--include-diffs/--no-include-diffs", help="Include commit diffs for AI."
    ),
    no_prs: Optional[bool] = typer.Option(None, help="Skip PR lookups."),
    no_merge_commits: Optional[bool] = typer.Option(None, help="Exclude merge commits."),
    max_items: Optional[int] = typer.Option(None, help="Limit commits."),
    summary_cache: Optional[Path] = typer.Option(None, help="Cache file path."),
    fail_on_empty: Optional[bool] = typer.Option(None, help="Exit on no commits."),
    domain_scope: Optional[str] = typer.Option(
        None,
        help="Domain scope for the system prompt (e.g., 'software release notes', 'conservation').",
    ),
    expert_role: Optional[List[str]] = typer.Option(
        None,
        "--expert-role",
        help="Add a role for multi-expert prompting (repeatable). Defaults: Product Manager, Tech Lead, QA Engineer.",
    ),
    rag_backend: Optional[RagBackend] = typer.Option(
        None,
        help="RAG backend: 'simple' (keyword) or 'chroma' (best-effort, optional dependency).",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Custom Jinja2 template file for output formatting.",
    ),
    use_builtin_templates: bool = typer.Option(
        False,
        "--use-builtin-templates",
        help="Use bundled Jinja2 templates instead of hardcoded formatters.",
    ),
    include_types: Optional[List[str]] = typer.Option(
        None,
        "--include-types",
        help="Only include commits of these types (space-separated: feat fix docs).",
    ),
    exclude_scopes: Optional[List[str]] = typer.Option(
        None,
        "--exclude-scopes",
        help="Exclude commits with these scopes (space-separated: deps ci).",
    ),
    author_filter: Optional[str] = typer.Option(
        None,
        "--author-filter",
        help="Regex pattern to filter commits by author name or email.",
    ),
) -> None:
    """Generate release notes from commit history."""

    repo = repo.resolve()

    # Load config file from repo (or explicit config path)
    file_config = load_config(repo, config_file=config)

    # Apply config file values as defaults (CLI options override)
    if output_format is None:
        output_format = OutputFormat(file_config.generate.format)
    if use_llm is None:
        use_llm = file_config.ai.enabled
    if llm_provider is None:
        llm_provider = file_config.ai.provider
    if openai_model is None:
        openai_model = file_config.ai.openai_model
    if openrouter_model is None:
        openrouter_model = file_config.ai.openrouter_model
    if include_scopes is None:
        include_scopes = file_config.generate.include_scopes
    if include_diffs is None:
        include_diffs = file_config.ai.include_diffs
    if no_prs is None:
        no_prs = file_config.generate.no_prs
    if no_merge_commits is None:
        no_merge_commits = file_config.generate.no_merge_commits
    if fail_on_empty is None:
        fail_on_empty = file_config.generate.fail_on_empty
    if domain_scope is None:
        domain_scope = file_config.ai.domain_scope
    if expert_role is None and file_config.ai.expert_roles:
        expert_role = file_config.ai.expert_roles
    if rag_backend is None:
        rag_backend = RagBackend(file_config.ai.rag_backend)
    if include_types is None and file_config.generate.include_types:
        include_types = file_config.generate.include_types
    if exclude_scopes is None and file_config.generate.exclude_scopes:
        exclude_scopes = file_config.generate.exclude_scopes
    if author_filter is None:
        author_filter = file_config.generate.author_filter

    git_repo = GitRepository(repo)

    commit_range, context = _resolve_commit_range(
        git_repo,
        since_tag=since_tag,
        until_tag=until_tag,
        since=since,
        until=until,
        since_date=since_date,
        until_date=until_date,
        unreleased=unreleased,
        include_merges=not no_merge_commits,
        max_items=max_items,
    )

    commits = list(git_repo.iter_commits(commit_range, include_diffs=include_diffs))

    # Apply filtering
    commits = filter_commits(
        commits,
        include_types=include_types,
        exclude_scopes=exclude_scopes,
        author_filter=author_filter,
    )

    if not commits:
        message = "No commits found for the selected range."
        if fail_on_empty:
            typer.echo(message, err=True)
            raise typer.Exit(code=1)
        typer.echo(message)
        return

    # Detect platform and attach PR/MR numbers
    github_slug = git_repo.get_github_slug()
    gitlab_slug = git_repo.get_gitlab_slug()
    bitbucket_slug = git_repo.get_bitbucket_slug()
    platform: Optional[str] = None
    if github_slug:
        platform = "github"
        _attach_pr_numbers(commits)
    elif gitlab_slug:
        platform = "gitlab"
        _attach_mr_numbers(commits)
    elif bitbucket_slug:
        platform = "bitbucket"
        _attach_bb_pr_numbers(commits)
    else:
        _attach_pr_numbers(commits)

    pr_index: Dict[int, PullRequestInfo] = {}
    commit_prs: Dict[str, List[PullRequestInfo]] = {}
    github_client: Optional[GitHubClient] = None
    gitlab_client: Optional[GitLabClient] = None
    bitbucket_client: Optional[BitbucketClient] = None
    try:
        if not no_prs:
            if platform == "github" and github_slug:
                settings = GitHubSettings(
                    owner=github_slug[0], repo=github_slug[1], token=github_token
                )
                github_client = GitHubClient(settings)
                pr_index, commit_prs = _enrich_with_pull_requests(github_client, commits)
            elif platform == "gitlab" and gitlab_slug:
                settings = GitLabSettings(project_path=gitlab_slug, token=gitlab_token)
                gitlab_client = GitLabClient(settings)
                pr_index, commit_prs = _enrich_with_merge_requests(gitlab_client, commits)
            elif platform == "bitbucket" and bitbucket_slug:
                settings = BitbucketSettings(
                    workspace=bitbucket_slug[0], repo_slug=bitbucket_slug[1], token=bitbucket_token
                )
                bitbucket_client = BitbucketClient(settings)
                pr_index, commit_prs = _enrich_with_bitbucket_pull_requests(bitbucket_client, commits)
    finally:
        if github_client:
            github_client.close()
        if gitlab_client:
            gitlab_client.close()
        if bitbucket_client:
            bitbucket_client.close()

    summarizer: Optional[BaseSummarizer] = None
    if use_llm:
        # Validate API key before attempting to use LLM
        try:
            if llm_provider.lower() == "openrouter":
                validated_key = _validate_api_key("openrouter", openrouter_api_key)
            else:
                validated_key = _validate_api_key("openai", openai_api_key)
        except MissingApiKeyError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=1) from None

        cache_path = summary_cache or (repo / DEFAULT_SUMMARY_CACHE)
        rag_backend_value = rag_backend.value
        summarizer_kwargs = {
            "cache_path": cache_path,
            "domain_scope": domain_scope,
            "expert_roles": expert_role,
            "rag_backend": rag_backend_value,
        }
        if llm_provider.lower() == "openrouter":
            summarizer = PromptEngineeredSummarizer(
                api_key=validated_key,
                model=openrouter_model,
                base_url="https://openrouter.ai/api/v1",
                **summarizer_kwargs,
            )
        else:
            summarizer = PromptEngineeredSummarizer(
                api_key=validated_key,
                model=openai_model,
                **summarizer_kwargs,
            )

    # Build changelog
    builder = ChangelogBuilder(
        summarizer=summarizer,
        include_scopes=include_scopes,
    )

    version_name = context.until_tag.name if context.until_tag else "Unreleased"
    tag_date = getattr(context.until_tag, "date", None) if context.until_tag else None
    release_date = tag_date if tag_date else datetime.now(timezone.utc)

    changelog = builder.build(
        version=version_name,
        release_date=release_date,
        commits=commits,
        commit_prs=commit_prs,
        pr_index=pr_index,
    )

    compare_url = _compute_compare_url(github_slug, gitlab_slug, bitbucket_slug, context)
    if compare_url:
        changelog.metadata["compare_url"] = compare_url

    # Determine template path: CLI flag > config file > None
    template_path = template
    if template_path is None:
        template_path = file_config.templates.get_template_for_format(output_format.value)

    output = _render_output(
        changelog,
        output_format,
        template_path=template_path,
        use_templates=use_builtin_templates or template_path is not None,
    )
    _write_output(output, out)
    typer.echo(
        f"Generated changelog with {sum(len(section.items) for section in changelog.sections)} entries."
    )


@app.command()
def auto_commit(
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="Repository path.",
    ),
    openai_api_key: Optional[str] = typer.Option(
        None, envvar="OPENAI_API_KEY", help="OpenAI API key."
    ),
    openai_model: str = typer.Option("gpt-4o-mini", help="OpenAI model."),
    summary_cache: Optional[Path] = typer.Option(None, help="Cache file path."),
) -> None:
    """Automatically generate a commit message from current changes and commit."""
    git_repo = GitRepository(repo)
    if not git_repo.is_dirty():
        typer.echo("No changes to commit.")
        raise typer.Exit()

    summarizer = PromptEngineeredSummarizer(
        api_key=openai_api_key,
        model=openai_model,
        cache_path=summary_cache,
        domain_scope="git commit messages",
    )

    while True:
        diff = git_repo.get_diff(staged=False)
        if not diff.strip():
            # If diff is empty, it might be because of untracked files.
            # We stage all to ensure we capture everything intended for the commit.
            git_repo.stage_all()
            diff = git_repo.get_diff(staged=True)
            if not diff.strip():
                typer.echo("No changes found even after staging.")
                raise typer.Exit()

        request_id = str(uuid.uuid4())
        req = SummaryRequest(identifier=request_id, title="Current changes", body=diff)

        typer.echo("Generating commit message...")
        results = list(summarizer.summarize([req]))
        summary = results[0].summary

        date_str = datetime.now().strftime("%Y-%m-%d")
        commit_message = f"{date_str}: {summary}"

        typer.echo(f"\nProposed commit message:\n{commit_message}\n")

        choice = typer.prompt("Commit? (y)es, (n)o, (r)etry, (e)dit", default="y").lower()

        if choice == "y":
            git_repo.stage_all()
            git_repo.commit(commit_message)
            typer.echo("Committed.")
            break
        elif choice == "n":
            typer.echo("Aborted.")
            raise typer.Exit()
        elif choice == "r":
            continue
        elif choice == "e":
            new_message = typer.prompt("Enter commit message", default=commit_message)
            git_repo.stage_all()
            git_repo.commit(new_message)
            typer.echo("Committed.")
            break


@app.command()
def generate_commit(
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="Repository path.",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to config file (.helixcommit.toml or .helixcommit.yaml).",
    ),
    llm_provider: Optional[str] = typer.Option(
        None, help="AI provider (openai/openrouter)."
    ),
    openai_model: Optional[str] = typer.Option(None, help="OpenAI model."),
    openai_api_key: Optional[str] = typer.Option(
        None, envvar="OPENAI_API_KEY", help="OpenAI API key."
    ),
    openrouter_model: Optional[str] = typer.Option(None, help="OpenRouter model."),
    openrouter_api_key: Optional[str] = typer.Option(
        None, envvar="OPENROUTER_API_KEY", help="OpenRouter API key."
    ),
    no_confirm: bool = typer.Option(False, help="Skip confirmation (not recommended)."),
) -> None:
    """Generate a commit message from staged changes."""
    repo = repo.resolve()

    # Load config file from repo (or explicit config path)
    file_config = load_config(repo, config_file=config)

    # Apply config file values as defaults (CLI options override)
    if llm_provider is None:
        llm_provider = file_config.ai.provider
    if openai_model is None:
        openai_model = file_config.ai.openai_model
    if openrouter_model is None:
        openrouter_model = file_config.ai.openrouter_model

    # 1. Setup Git
    git_repo = GitRepository(repo)

    # 2. Check for staged changes
    diff = git_repo.get_diff(staged=True)
    if not diff.strip():
        typer.echo("No staged changes found. Stage some changes with 'git add' first.")
        raise typer.Exit(1)

    # 3. Setup AI - validate API key
    try:
        api_key = _validate_api_key(
            llm_provider,
            openrouter_api_key if llm_provider == "openrouter" else openai_api_key,
        )
    except MissingApiKeyError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None

    model = openrouter_model if llm_provider == "openrouter" else openai_model
    base_url = "https://openrouter.ai/api/v1" if llm_provider == "openrouter" else None

    try:
        generator = CommitGenerator(api_key=api_key, model=model, base_url=base_url)
    except ImportError as e:
        typer.echo(str(e))
        raise typer.Exit(1) from None

    # 4. Generate
    typer.echo("Analyzing changes...")
    response = generator.generate(diff)

    # 5. Interactive Loop
    while True:
        typer.echo("\nAI Response:")
        typer.echo("--------------------------------------------------")
        typer.echo(response)
        typer.echo("--------------------------------------------------")

        if no_confirm:
            # If no confirm, we assume the response IS the message.
            # But we still need to format it.
            pass

        choice = typer.prompt(
            "\nAction? [c]ommit / [r]eply / [q]uit", default="c"
        ).lower()

        if choice == "q":
            typer.echo("Aborted.")
            raise typer.Exit(0)

        elif choice == "c":
            # Extract potential message from response
            match = re.search(r"\d{2}-\d{2}-\d{4}: .+", response)
            if match:
                commit_msg = match.group(0)
            else:
                # Prepend date if missing
                today_str = datetime.now().strftime("%m-%d-%Y")
                if response.strip().startswith(today_str):
                    commit_msg = response.strip()
                else:
                    commit_msg = f"{today_str}: {response.strip()}"

            confirm = typer.confirm(f"Commit with message:\n'{commit_msg}'?")
            if confirm:
                git_repo.commit(commit_msg)
                typer.echo("Committed!")
                break
            else:
                typer.echo("Commit cancelled. You can reply to refine.")

        elif choice == "r":
            user_feedback = typer.prompt("Your reply")
            response = generator.chat(user_feedback)


def _resolve_commit_range(
    repo: GitRepository,
    *,
    since_tag: Optional[str],
    until_tag: Optional[str],
    since: Optional[str],
    until: Optional[str],
    since_date: Optional[str],
    until_date: Optional[str],
    unreleased: bool,
    include_merges: bool,
    max_items: Optional[int],
) -> Tuple[CommitRange, RangeContext]:
    tags = repo.list_tags()

    resolved_since_tag = _find_tag(tags, since_tag) if since_tag else None
    resolved_until_tag = _find_tag(tags, until_tag) if until_tag else None

    since_ref = resolved_since_tag.name if resolved_since_tag else since
    until_ref = resolved_until_tag.name if resolved_until_tag else until or "HEAD"

    if unreleased and not since_ref:
        latest_tag = resolved_since_tag or (tags[0] if tags else None)
        if latest_tag:
            since_ref = latest_tag.name
            resolved_since_tag = latest_tag

    # Parse date filters if provided
    parsed_since_date = _parse_date(since_date) if since_date else None
    parsed_until_date = _parse_date(until_date) if until_date else None

    commit_range = CommitRange(
        since=since_ref,
        until=until_ref,
        since_date=parsed_since_date,
        until_date=parsed_until_date,
        include_merges=include_merges,
        max_count=max_items,
    )

    context = RangeContext(
        since_ref=since_ref,
        until_ref=until_ref,
        since_tag=resolved_since_tag,
        until_tag=resolved_until_tag,
    )
    return commit_range, context


def _find_tag(tags: Sequence[TagInfo], name: Optional[str]) -> Optional[TagInfo]:
    if not name:
        return None
    for tag in tags:
        if tag.name == name:
            return tag
    return None


def _attach_pr_numbers(commits: Iterable[CommitInfo]) -> None:
    """Attach GitHub PR numbers to commits."""
    for commit in commits:
        pr_number = (
            _extract_pr_number(commit.subject)
            or _extract_pr_number(commit.body)
            or _extract_pr_number(commit.message)
        )
        if pr_number:
            commit.pr_number = pr_number


def _attach_mr_numbers(commits: Iterable[CommitInfo]) -> None:
    """Attach GitLab MR numbers to commits."""
    for commit in commits:
        mr_number = (
            _extract_mr_number(commit.subject)
            or _extract_mr_number(commit.body)
            or _extract_mr_number(commit.message)
        )
        if mr_number:
            commit.pr_number = mr_number


def _extract_pr_number(message: Optional[str]) -> Optional[int]:
    """Extract GitHub PR number from a message."""
    if not message:
        return None
    match = PR_NUMBER_PATTERN.search(message)
    if match:
        for group_name in ("num_paren", "num_pr", "num_alt"):
            value = match.group(group_name)
            if value:
                return int(value)
    merge_match = MERGE_PR_PATTERN.search(message)
    if merge_match:
        return int(merge_match.group(1))
    return None


def _extract_mr_number(message: Optional[str]) -> Optional[int]:
    """Extract GitLab MR number from a message."""
    if not message:
        return None
    match = MR_NUMBER_PATTERN.search(message)
    if match:
        for group_name in ("num_paren", "num_mr", "num_alt"):
            value = match.group(group_name)
            if value:
                return int(value)
    return None


def _enrich_with_pull_requests(
    client: GitHubClient,
    commits: Sequence[CommitInfo],
) -> Tuple[Dict[int, PullRequestInfo], Dict[str, List[PullRequestInfo]]]:
    """Enrich commits with GitHub pull request information."""
    pr_index: Dict[int, PullRequestInfo] = {}
    commit_prs: Dict[str, List[PullRequestInfo]] = {}

    unique_numbers = sorted(
        {int(commit.pr_number) for commit in commits if commit.pr_number is not None}
    )
    for number in unique_numbers:
        pr = client.get_pull_request(number)
        if pr:
            pr_index[number] = pr

    for commit in commits:
        if commit.pr_number and commit.pr_number in pr_index:
            continue
        prs = client.find_pull_requests_by_commit(commit.sha)
        if prs:
            commit_prs[commit.sha] = prs
            if not commit.pr_number:
                commit.pr_number = prs[0].number
                pr_index.setdefault(prs[0].number, prs[0])
    return pr_index, commit_prs


def _enrich_with_merge_requests(
    client: GitLabClient,
    commits: Sequence[CommitInfo],
) -> Tuple[Dict[int, PullRequestInfo], Dict[str, List[PullRequestInfo]]]:
    """Enrich commits with GitLab merge request information."""
    mr_index: Dict[int, PullRequestInfo] = {}
    commit_mrs: Dict[str, List[PullRequestInfo]] = {}

    unique_iids = sorted(
        {int(commit.pr_number) for commit in commits if commit.pr_number is not None}
    )
    for iid in unique_iids:
        mr = client.get_merge_request(iid)
        if mr:
            mr_index[iid] = mr

    for commit in commits:
        if commit.pr_number and commit.pr_number in mr_index:
            continue
        mrs = client.find_merge_requests_by_commit(commit.sha)
        if mrs:
            commit_mrs[commit.sha] = mrs
            if not commit.pr_number:
                commit.pr_number = mrs[0].number
                mr_index.setdefault(mrs[0].number, mrs[0])
    return mr_index, commit_mrs


def _attach_bb_pr_numbers(commits: Iterable[CommitInfo]) -> None:
    """Attach Bitbucket PR numbers to commits."""
    for commit in commits:
        pr_number = (
            _extract_bb_pr_number(commit.subject)
            or _extract_bb_pr_number(commit.body)
            or _extract_bb_pr_number(commit.message)
        )
        if pr_number:
            commit.pr_number = pr_number


def _extract_bb_pr_number(message: Optional[str]) -> Optional[int]:
    """Extract Bitbucket PR number from a message."""
    if not message:
        return None
    match = BB_PR_NUMBER_PATTERN.search(message)
    if match:
        for group_name in ("num_pr", "num_alt", "num_merged"):
            value = match.group(group_name)
            if value:
                return int(value)
    return None


def _enrich_with_bitbucket_pull_requests(
    client: BitbucketClient,
    commits: Sequence[CommitInfo],
) -> Tuple[Dict[int, PullRequestInfo], Dict[str, List[PullRequestInfo]]]:
    """Enrich commits with Bitbucket pull request information."""
    pr_index: Dict[int, PullRequestInfo] = {}
    commit_prs: Dict[str, List[PullRequestInfo]] = {}

    unique_ids = sorted(
        {int(commit.pr_number) for commit in commits if commit.pr_number is not None}
    )
    for pr_id in unique_ids:
        pr = client.get_pull_request(pr_id)
        if pr:
            pr_index[pr_id] = pr

    for commit in commits:
        if commit.pr_number and commit.pr_number in pr_index:
            continue
        prs = client.find_pull_requests_by_commit(commit.sha)
        if prs:
            commit_prs[commit.sha] = prs
            if not commit.pr_number:
                commit.pr_number = prs[0].number
                pr_index.setdefault(prs[0].number, prs[0])
    return pr_index, commit_prs


def _compute_compare_url(
    github_slug: Optional[Tuple[str, str]],
    gitlab_slug: Optional[str],
    bitbucket_slug: Optional[Tuple[str, str]],
    context: RangeContext,
) -> Optional[str]:
    """Compute a comparison URL for GitHub, GitLab, or Bitbucket."""
    if not context.since_ref or not context.until_ref:
        return None
    if github_slug:
        owner, repo = github_slug
        return f"https://github.com/{owner}/{repo}/compare/{context.since_ref}...{context.until_ref}"
    if gitlab_slug:
        return f"https://gitlab.com/{gitlab_slug}/-/compare/{context.since_ref}...{context.until_ref}"
    if bitbucket_slug:
        workspace, repo_slug = bitbucket_slug
        return f"https://bitbucket.org/{workspace}/{repo_slug}/branches/compare/{context.until_ref}%0D{context.since_ref}"
    return None


def _render_output(
    changelog: Changelog,
    output_format: OutputFormat,
    template_path: Optional[Path] = None,
    use_templates: bool = False,
) -> str:
    """Render changelog output using formatters or templates.

    Args:
        changelog: The changelog to render.
        output_format: The output format (markdown, html, text, json, yaml).
        template_path: Optional custom template file path.
        use_templates: If True, use Jinja2 templates instead of hardcoded formatters.

    Returns:
        The rendered changelog as a string.
    """
    # Use templates if explicitly requested or if a custom template is provided
    if use_templates or template_path:
        engine = TemplateEngine()
        return engine.render(changelog, output_format.value, template_path)

    # Fall back to hardcoded formatters
    if output_format is OutputFormat.markdown:
        return markdown_formatter.render_markdown(changelog)
    if output_format is OutputFormat.html:
        return html_formatter.render_html(changelog)
    if output_format is OutputFormat.text:
        return text_formatter.render_text(changelog)
    if output_format is OutputFormat.json:
        return json_formatter.render_json(changelog)
    if output_format is OutputFormat.yaml:
        return yaml_formatter.render_yaml(changelog)
    raise typer.BadParameter(f"Unsupported format: {output_format}")


def _write_output(content: str, destination: Optional[Path]) -> None:
    if destination:
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        typer.echo(f"Wrote changelog to {destination}")
    else:
        typer.echo(content)


def main() -> None:  # pragma: no cover - console entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
