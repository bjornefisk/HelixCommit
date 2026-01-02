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

from . import __version__
from .changelog import ChangelogBuilder, filter_commits
from .commit_generator import CommitGenerator
from .config import load_config
from .formatters import html as html_formatter
from .formatters import json as json_formatter
from .formatters import markdown as markdown_formatter
from .formatters import text as text_formatter
from .formatters import yaml as yaml_formatter
from .grouper import SECTION_ALIASES, SECTION_TITLES
from .template import TemplateEngine, detect_format_from_template
from .bitbucket_client import BitbucketClient, BitbucketSettings
from .git_client import CommitRange, GitRepository, TagInfo
from .github_client import GitHubClient, GitHubSettings
from .gitlab_client import GitLabClient, GitLabSettings
from .models import Changelog, CommitInfo, PullRequestInfo
from .summarizer import BaseSummarizer, PromptEngineeredSummarizer, SummaryRequest
from .ui import get_console, set_theme
from .ui.panels import error_panel, success_panel, info_panel
from .ui.spinners import ai_spinner, TaskProgress

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


class ThemeChoice(str, Enum):
    """Theme choices for the CLI."""
    dark = "dark"
    light = "light"
    auto = "auto"


def _typer_app() -> typer.Typer:
    return typer.Typer(
        help="Generate release notes from Git repositories.",
        no_args_is_help=True,
        rich_markup_mode="rich",
    )


app = _typer_app()


def _version_callback(value: bool) -> bool:
    if value:
        console = get_console()
        console.print(f"[bold primary]{APP_NAME}[/] [muted]v{__version__}[/]")
        raise typer.Exit()
    return value


def _theme_callback(value: Optional[ThemeChoice]) -> Optional[ThemeChoice]:
    """Set the theme when provided."""
    if value is not None:
        set_theme(value.value)
    return value


@app.callback()
def _main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show HelixCommit version and exit.",
    ),
    theme: Optional[ThemeChoice] = typer.Option(
        None,
        "--theme",
        "-t",
        callback=_theme_callback,
        is_eager=True,
        help="Color theme: dark, light, or auto.",
        case_sensitive=False,
    ),
) -> None:
    """[bold cyan]HelixCommit[/] - AI-powered release notes generator.
    
    Generate beautiful release notes from your Git commit history with AI-powered summarization.
    """
    console = get_console()

    # Show a lightweight community banner for interactive runs (avoids polluting redirected output)
    if console.is_terminal:
        console.print(
            info_panel(
                "[primary]Join the HelixCommit community on Discord[/]\n"
                "Bug reports, release previews, docs feedback, and Q&A: "
                "https://discord.gg/UewHHrxNRE",
                title="Community & Support",
            )
        )
    return


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
    include_paths: Optional[List[str]] = typer.Option(
        None,
        "--include-paths",
        help="Only include commits touching these paths (supports glob patterns).",
    ),
    exclude_paths: Optional[List[str]] = typer.Option(
        None,
        "--exclude-paths",
        help="Exclude commits touching these paths (supports glob patterns).",
    ),
    section_order: Optional[List[str]] = typer.Option(
        None,
        "--section-order",
        help="Custom section ordering (repeatable, e.g., --section-order fix --section-order feat).",
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
    if include_paths is None and file_config.generate.include_paths:
        include_paths = file_config.generate.include_paths
    if exclude_paths is None and file_config.generate.exclude_paths:
        exclude_paths = file_config.generate.exclude_paths
    if section_order is None and file_config.generate.section_order:
        section_order = file_config.generate.section_order
    if author_filter is None:
        author_filter = file_config.generate.author_filter

    console = get_console()
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

    if include_paths:
        commit_range.paths = tuple(include_paths)

    normalized_section_order = _normalize_section_order(section_order)
    if section_order and not normalized_section_order:
        console.print(error_panel(
            "--section-order only accepts known section keys or titles (e.g., feat, fix, docs).",
            title="Invalid Parameter",
        ))
        raise typer.Exit(code=1)

    collect_files = bool(include_paths or exclude_paths)
    
    # Collect commits with progress indicator
    with console.status("[progress.spinner]Scanning commits...[/]", spinner="dots"):
        commits = list(
            git_repo.iter_commits(
                commit_range,
                include_diffs=include_diffs,
                include_files=collect_files,
            )
        )

    # Apply filtering
    commits = filter_commits(
        commits,
        include_types=include_types,
        exclude_scopes=exclude_scopes,
        author_filter=author_filter,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
    )

    if not commits:
        message = "No commits found for the selected range."
        if fail_on_empty:
            console.print(error_panel(message, title="No Commits"))
            raise typer.Exit(code=1)
        console.print(info_panel(message, title="No Commits"))
        return
    
    console.print(f"[muted]Found[/] [primary]{len(commits)}[/] [muted]commits to process[/]")

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
            with console.status("[progress.spinner]Fetching pull request information...[/]", spinner="dots"):
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
            console.print(error_panel(
                str(e),
                title="Missing API Key",
                hint="Set the environment variable or pass it via command line.",
            ))
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
        console.print(f"[muted]Using AI provider:[/] [primary]{llm_provider}[/]")

    # Build changelog
    builder = ChangelogBuilder(
        summarizer=summarizer,
        include_scopes=include_scopes,
        section_order=normalized_section_order,
    )

    version_name = context.until_tag.name if context.until_tag else "Unreleased"
    tag_date = getattr(context.until_tag, "date", None) if context.until_tag else None
    release_date = tag_date if tag_date else datetime.now(timezone.utc)

    # Build changelog with AI spinner if using LLM
    if use_llm:
        with console.status("[progress.spinner]Generating AI summaries...[/]", spinner="dots"):
            changelog = builder.build(
                version=version_name,
                release_date=release_date,
                commits=commits,
                commit_prs=commit_prs,
                pr_index=pr_index,
            )
    else:
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
    _write_output(output, out, console)
    
    # Summary stats
    total_entries = sum(len(section.items) for section in changelog.sections)
    console.print(success_panel(
        f"Generated changelog with {total_entries} entries",
        title="Success",
        details=f"Version: {version_name} | Format: {output_format.value}",
    ))


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
    show_diff: bool = typer.Option(True, "--show-diff/--no-show-diff", help="Show staged diff preview."),
) -> None:
    """Generate a commit message from staged changes."""
    from .ui.panels import diff_panel
    from rich.panel import Panel
    from rich.text import Text
    
    console = get_console()
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
        console.print(error_panel(
            "No staged changes found.",
            title="No Changes",
            hint="Stage some changes with 'git add' first.",
        ))
        raise typer.Exit(1)

    # Show diff preview if requested
    if show_diff:
        console.print()
        staged_files_output = git_repo._run_git("diff", "--cached", "--name-only").strip()
        if staged_files_output:
            staged_files = staged_files_output.splitlines()
            panel_content = Text("\n".join(f"- {f}" for f in staged_files))
            console.print(Panel(panel_content, title="[primary]Staged Files[/]", border_style="primary"))
        else:
            console.print(Panel(Text("No files staged."), title="[primary]Staged Files[/]", border_style="primary"))
        console.print()

    # 3. Setup AI - validate API key
    try:
        api_key = _validate_api_key(
            llm_provider,
            openrouter_api_key if llm_provider == "openrouter" else openai_api_key,
        )
    except MissingApiKeyError as e:
        console.print(error_panel(
            str(e),
            title="Missing API Key",
            hint="Set the environment variable or pass it via command line.",
        ))
        raise typer.Exit(1) from None

    model = openrouter_model if llm_provider == "openrouter" else openai_model
    base_url = "https://openrouter.ai/api/v1" if llm_provider == "openrouter" else None

    try:
        generator = CommitGenerator(api_key=api_key, model=model, base_url=base_url)
    except ImportError as e:
        console.print(error_panel(str(e), title="Import Error"))
        raise typer.Exit(1) from None

    # 4. Generate with streaming
    from rich.live import Live
    from rich.text import Text
    from rich.panel import Panel

    # Initialize with empty content
    current_content = ""
    response_panel = Panel(
        Text(current_content or "Generating..."),
        title="[primary]Proposed Commit Message[/]",
        border_style="primary",
    )

    def update_panel(delta: str) -> None:
        nonlocal current_content
        current_content += delta
        response_panel.renderable = Text(current_content)
        live.update(response_panel)

    with Live(response_panel, console=console, refresh_per_second=10) as live:
        response = generator.generate(diff, stream=True, stream_callback=update_panel)

    # 5. Interactive Loop
    def _ensure_text(value: object) -> str:
        """Best-effort conversion to string, avoiding mock __str__ surprises."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return str(value)
        except Exception:
            try:
                return repr(value)
            except Exception:
                return ""

    while True:
        # Extract a displayable commit message and a clean subject for git
        raw_message = generator.to_message(response)
        subject_line = generator.to_subject(response)

        message_text = _ensure_text(raw_message).strip()
        subject_text = _ensure_text(subject_line).strip()

        commit_msg = subject_text or message_text
        panel_text = (
            message_text
            if isinstance(raw_message, str) and message_text
            else commit_msg or "(empty response)"
        )

        # Update the panel with final cleaned content
        response_panel.renderable = Text(panel_text)
        console.print()
        console.print(response_panel)
        console.print()

        if no_confirm:
            # If no confirm, auto-commit
            pass

        console.print("[muted]c:[/] [primary]commit[/]  [muted]r:[/] [primary]reply[/]  [muted]q:[/] [primary]quit[/]")
        choice = typer.prompt("Choice").lower()

        if choice == "q":
            console.print(info_panel("Operation cancelled.", title="Aborted"))
            raise typer.Exit(0)

        elif choice == "c":
            confirm = typer.confirm("Commit with this message?")
            if confirm:
                git_repo.commit(commit_msg)
                # Show first line for details
                subject_line = commit_msg.split("\n")[0][:60]
                console.print(success_panel(
                    "Changes committed successfully!",
                    title="Committed",
                    details=f"Message: {subject_line}...",
                ))
                break
            else:
                console.print("[muted]Commit cancelled. You can reply to refine.[/]")

        elif choice == "r":
            user_feedback = typer.prompt("Your reply")
            with console.status("[progress.spinner]Processing your feedback...[/]", spinner="dots"):
                response = generator.chat(user_feedback)


@app.command()
def preview(
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="Repository path.",
    ),
    since_tag: Optional[str] = typer.Option(None, help="Commits after this tag."),
    until_tag: Optional[str] = typer.Option(None, help="Commits up to this tag."),
    since: Optional[str] = typer.Option(None, help="Commits after this ref."),
    until: Optional[str] = typer.Option(None, help="Commits up to this ref."),
    unreleased: bool = typer.Option(False, help="Show HEAD vs latest tag."),
    max_items: Optional[int] = typer.Option(None, help="Limit commits."),
    no_merge_commits: bool = typer.Option(False, help="Exclude merge commits."),
) -> None:
    """Preview changelog in a beautifully formatted panel.
    
    Shows a live preview of what your changelog will look like without 
    generating any files.
    """
    from .ui.panels import changelog_panel, section_panel
    from .ui.tables import commits_table, changelog_table
    from rich.console import Group
    from rich.rule import Rule
    
    console = get_console()
    repo = repo.resolve()
    git_repo = GitRepository(repo)

    commit_range, context = _resolve_commit_range(
        git_repo,
        since_tag=since_tag,
        until_tag=until_tag,
        since=since,
        until=until,
        since_date=None,
        until_date=None,
        unreleased=unreleased,
        include_merges=not no_merge_commits,
        max_items=max_items,
    )

    with console.status("[progress.spinner]Loading commits...[/]", spinner="dots"):
        commits = list(git_repo.iter_commits(commit_range))

    if not commits:
        console.print(info_panel("No commits found for the selected range.", title="Preview"))
        return

    # Show commit summary table
    console.print()
    console.print(Rule("[primary]Commit Preview[/]", style="primary"))
    console.print()
    console.print(commits_table(commits[:20], title=f"Recent Commits ({len(commits)} total)"))
    console.print()

    # Build a simple changelog preview
    builder = ChangelogBuilder(summarizer=None, include_scopes=True)
    version_name = context.until_tag.name if context.until_tag else "Unreleased"
    release_date = datetime.now(timezone.utc)

    changelog = builder.build(
        version=version_name,
        release_date=release_date,
        commits=commits,
    )

    # Show changelog preview
    console.print(Rule("[primary]Changelog Preview[/]", style="primary"))
    console.print()
    console.print(changelog_panel(changelog, show_metadata=False))
    console.print()
    
    # Summary stats
    total_entries = sum(len(section.items) for section in changelog.sections)
    section_counts = {section.title: len(section.items) for section in changelog.sections if section.items}
    
    console.print(f"[muted]Total entries:[/] [primary]{total_entries}[/]")
    for title, count in section_counts.items():
        console.print(f"  [muted]•[/] {title}: [accent]{count}[/]")


@app.command()
def browse(
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="Repository path.",
    ),
    since_tag: Optional[str] = typer.Option(None, help="Commits after this tag."),
    until_tag: Optional[str] = typer.Option(None, help="Commits up to this tag."),
    since: Optional[str] = typer.Option(None, help="Commits after this ref."),
    until: Optional[str] = typer.Option(None, help="Commits up to this ref."),
    unreleased: bool = typer.Option(False, help="Show HEAD vs latest tag."),
    max_items: int = typer.Option(50, help="Maximum commits to show."),
    no_merge_commits: bool = typer.Option(False, help="Exclude merge commits."),
    show_body: bool = typer.Option(False, "--show-body", help="Show commit bodies."),
) -> None:
    """Browse commits interactively with detailed views.
    
    Navigate through commits with arrow keys, view details, and explore
    your commit history in a rich terminal interface.
    """
    from .ui.panels import commit_panel
    from .ui.tables import commits_table
    from rich.panel import Panel
    from rich.text import Text
    from rich.rule import Rule
    
    console = get_console()
    repo = repo.resolve()
    git_repo = GitRepository(repo)

    commit_range, context = _resolve_commit_range(
        git_repo,
        since_tag=since_tag,
        until_tag=until_tag,
        since=since,
        until=until,
        since_date=None,
        until_date=None,
        unreleased=unreleased,
        include_merges=not no_merge_commits,
        max_items=max_items,
    )

    with console.status("[progress.spinner]Loading commits...[/]", spinner="dots"):
        commits = list(git_repo.iter_commits(commit_range))

    if not commits:
        console.print(info_panel("No commits found for the selected range.", title="Browse"))
        return

    console.print()
    console.print(Rule(f"[primary]Commit Browser[/] [muted]({len(commits)} commits)[/]", style="primary"))
    console.print()

    # Display all commits in a table
    console.print(commits_table(commits, title="Commits"))
    console.print()

    # Interactive mode - show details for selected commits
    current_index = 0
    while True:
        console.print()
        console.print(f"[muted]Viewing commit[/] [primary]{current_index + 1}[/] [muted]of[/] [primary]{len(commits)}[/]")
        console.print()
        
        commit = commits[current_index]
        console.print(commit_panel(commit, show_body=show_body, show_diff=False))
        console.print()
        
        console.print("[muted]Navigation:[/] [primary][n][/]ext  [primary][p][/]rev  [primary][d][/]iff  [primary][q][/]uit")
        choice = typer.prompt("Choice", default="n").lower()
        
        if choice == "q":
            break
        elif choice == "n":
            current_index = min(current_index + 1, len(commits) - 1)
        elif choice == "p":
            current_index = max(current_index - 1, 0)
        elif choice == "d":
            # Show diff for current commit
            diff = git_repo.get_commit_diff(commit.sha)
            if diff:
                from .ui.panels import diff_panel
                console.print(diff_panel(diff, title=f"Diff for {commit.short_sha()}"))
            else:
                console.print("[muted]No diff available for this commit.[/]")
        
        console.clear()


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (searches subject, author, body)."),
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="Repository path.",
    ),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Filter by author (regex)."),
    commit_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by commit type (feat, fix, etc.)."),
    since_tag: Optional[str] = typer.Option(None, help="Search commits after this tag."),
    until_tag: Optional[str] = typer.Option(None, help="Search commits up to this tag."),
    since: Optional[str] = typer.Option(None, help="Search commits after this ref."),
    until: Optional[str] = typer.Option(None, help="Search commits up to this ref."),
    max_results: int = typer.Option(50, help="Maximum results to show."),
    case_sensitive: bool = typer.Option(False, "--case-sensitive", help="Case-sensitive search."),
) -> None:
    """Search commits by keyword, author, or type.
    
    Quickly find commits matching your search criteria with highlighted
    results and detailed information.
    """
    from .ui.tables import search_results_table
    from .ui.panels import commit_panel
    from rich.rule import Rule
    import re as regex_module
    
    console = get_console()
    repo = repo.resolve()
    git_repo = GitRepository(repo)

    commit_range, context = _resolve_commit_range(
        git_repo,
        since_tag=since_tag,
        until_tag=until_tag,
        since=since,
        until=until,
        since_date=None,
        until_date=None,
        unreleased=False,
        include_merges=True,
        max_items=500,  # Search through more commits
    )

    with console.status(f"[progress.spinner]Searching for '{query}'...[/]", spinner="dots"):
        all_commits = list(git_repo.iter_commits(commit_range))
        
        # Build search pattern
        flags = 0 if case_sensitive else regex_module.IGNORECASE
        try:
            pattern = regex_module.compile(query, flags)
        except regex_module.error:
            # Fall back to literal search if regex is invalid
            pattern = regex_module.compile(regex_module.escape(query), flags)
        
        # Filter commits
        results = []
        for commit in all_commits:
            # Check query against subject, body, author
            searchable = f"{commit.subject} {commit.body} {commit.author_name} {commit.author_email}"
            if not pattern.search(searchable):
                continue
            
            # Apply author filter
            if author:
                author_pattern = regex_module.compile(author, regex_module.IGNORECASE)
                if not author_pattern.search(f"{commit.author_name} {commit.author_email}"):
                    continue
            
            # Apply type filter
            if commit_type:
                parsed_type = _extract_commit_type_from_subject(commit.subject)
                if parsed_type != commit_type.lower():
                    continue
            
            results.append(commit)
            if len(results) >= max_results:
                break

    console.print()
    console.print(Rule(f"[primary]Search Results[/] [muted]for '{query}'[/]", style="primary"))
    console.print()

    if not results:
        console.print(info_panel(
            f"No commits found matching '{query}'",
            title="No Results",
        ))
        return

    console.print(search_results_table(results, query=query, highlight_matches=True))
    console.print()
    console.print(f"[muted]Found[/] [primary]{len(results)}[/] [muted]matching commits[/]")
    
    # Offer to view details
    if results and typer.confirm("\nView commit details?", default=False):
        for i, commit in enumerate(results[:10]):
            console.print()
            console.print(f"[muted]Result {i + 1} of {min(len(results), 10)}[/]")
            console.print(commit_panel(commit, show_body=True))
            if i < min(len(results), 10) - 1:
                if not typer.confirm("Show next?", default=True):
                    break


def _extract_commit_type_from_subject(subject: str) -> Optional[str]:
    """Extract commit type from a conventional commit subject."""
    match = re.match(r"^(\w+)(?:\([^)]+\))?[!:]", subject)
    if match:
        return match.group(1).lower()
    return None


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


def _write_output(content: str, destination: Optional[Path], console=None) -> None:
    if console is None:
        console = get_console()
    
    if destination:
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        console.print(f"[muted]Wrote changelog to[/] [primary]{destination}[/]")
    else:
        # Print the raw content (not styled, for piping/file output compatibility)
        console.print(content, markup=False, highlight=False)


def _normalize_section_order(values: Optional[Sequence[str]]) -> Optional[List[str]]:
    if not values:
        return None
    seen = set()
    normalized: List[str] = []
    for value in values:
        canonical = _canonical_section_key(value)
        if canonical and canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)
    return normalized or None


def _canonical_section_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip().lower()
    if not key:
        return None
    if key in SECTION_TITLES:
        return key
    if key in SECTION_ALIASES:
        return SECTION_ALIASES[key]
    for canonical, title in SECTION_TITLES.items():
        if title.lower() == key:
            return canonical
    return None


def main() -> None:  # pragma: no cover - console entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
