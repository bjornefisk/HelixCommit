"""Configuration helpers for HelixCommit."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_TEMPLATE_DIR = Path(__file__).with_suffix("").parent / "formatters"

# Pattern for environment variable expansion: ${VAR} or ${VAR:-default}
ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def expand_env_vars(value: str) -> str:
    """Expand environment variables in a string value.

    Supports two syntaxes:
    - ${VAR} - replaced with the value of VAR, or kept as-is if not set
    - ${VAR:-default} - replaced with the value of VAR, or 'default' if not set

    Args:
        value: The string value potentially containing env var references.

    Returns:
        The string with environment variables expanded.
    """

    def replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)
        if var_name in os.environ:
            return os.environ[var_name]
        if default is not None:
            return default
        # Keep the original reference if var not set and no default
        return match.group(0)

    return ENV_VAR_PATTERN.sub(replace, value)

# Config file names in order of precedence
CONFIG_FILES = [".helixcommit.toml", ".helixcommit.yaml"]


@dataclass(slots=True)
class GeneratorConfig:
    """Configuration options for generating release notes."""

    repo_path: Path = field(default_factory=Path.cwd)
    since_ref: Optional[str] = None
    until_ref: Optional[str] = None
    include_unreleased: bool = False
    output_format: str = "markdown"
    output_file: Optional[Path] = None
    use_llm: bool = False
    openai_model: str = "gpt-4o-mini"
    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None
    bitbucket_token: Optional[str] = None
    template_path: Optional[Path] = None
    sections_order: Sequence[str] = field(default_factory=list)


@dataclass
class GenerateConfig:
    """Configuration options for the generate command."""

    format: str = "markdown"
    include_scopes: bool = True
    no_merge_commits: bool = False
    no_prs: bool = False
    fail_on_empty: bool = False
    include_types: List[str] = field(default_factory=list)
    exclude_scopes: List[str] = field(default_factory=list)
    author_filter: Optional[str] = None
    include_paths: List[str] = field(default_factory=list)
    exclude_paths: List[str] = field(default_factory=list)
    section_order: List[str] = field(default_factory=list)


@dataclass
class AIConfig:
    """Configuration options for AI features."""

    enabled: bool = False
    provider: str = "openrouter"
    openai_model: str = "gpt-4o-mini"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    include_diffs: bool = False
    domain_scope: Optional[str] = None
    expert_roles: List[str] = field(default_factory=list)
    rag_backend: str = "simple"


@dataclass
class TemplateConfig:
    """Configuration options for custom Jinja2 templates."""

    markdown: Optional[Path] = None
    html: Optional[Path] = None
    text: Optional[Path] = None
    json: Optional[Path] = None
    yaml: Optional[Path] = None

    def get_template_for_format(self, format_name: str) -> Optional[Path]:
        """Get the template path for a given format.

        Args:
            format_name: The format name (markdown, html, text, json, yaml).

        Returns:
            The template path if configured, otherwise None.
        """
        return getattr(self, format_name, None)


@dataclass
class FileConfig:
    """Parsed configuration from a config file."""

    generate: GenerateConfig = field(default_factory=GenerateConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    templates: TemplateConfig = field(default_factory=TemplateConfig)
    _source_path: Optional[Path] = None

    @property
    def source_path(self) -> Optional[Path]:
        """Return the path to the config file that was loaded."""
        return self._source_path


class ConfigLoader:
    """Loads configuration from .helixcommit.toml or .helixcommit.yaml files."""

    def __init__(
        self, repo_path: Optional[Path] = None, config_file: Optional[Path] = None
    ) -> None:
        """Initialize the config loader.

        Args:
            repo_path: Path to the repository root. Defaults to current directory.
            config_file: Explicit path to a config file. If provided, this file
                will be used instead of searching for config files in repo_path.
        """
        self.repo_path = (repo_path or Path.cwd()).resolve()
        self._config_file = config_file.resolve() if config_file else None
        self._config: Optional[FileConfig] = None
        self._loaded = False

    def find_config_file(self) -> Optional[Path]:
        """Find the config file to use.

        If an explicit config file was provided, returns that path.
        Otherwise, searches for config files in the repository root.

        Returns:
            Path to the config file, or None if not found.
        """
        # Use explicit config file if provided
        if self._config_file is not None:
            if self._config_file.is_file():
                return self._config_file
            return None

        # Search for config files in repo root
        for filename in CONFIG_FILES:
            config_path = self.repo_path / filename
            if config_path.is_file():
                return config_path
        return None

    def load(self) -> FileConfig:
        """Load configuration from the config file.

        Returns:
            FileConfig with parsed settings, or defaults if no file found.
        """
        if self._loaded:
            return self._config or FileConfig()

        self._loaded = True
        config_path = self.find_config_file()

        if config_path is None:
            self._config = FileConfig()
            return self._config

        try:
            if config_path.suffix == ".toml":
                data = self._load_toml(config_path)
            else:
                data = self._load_yaml(config_path)

            self._config = self._parse_config(data, config_path)
        except Exception:
            # If config file is invalid, use defaults
            self._config = FileConfig()

        return self._config

    def _load_toml(self, path: Path) -> Dict[str, Any]:
        """Load a TOML config file."""
        with open(path, "rb") as f:
            return tomllib.load(f)

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load a YAML config file."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}

    def _expand_config_data(
        self, data: Union[Dict[str, Any], List[Any], str, Any]
    ) -> Union[Dict[str, Any], List[Any], str, Any]:
        """Recursively expand environment variables in config data.

        Processes dictionaries, lists, and strings, expanding any ${VAR}
        or ${VAR:-default} patterns found in string values.

        Args:
            data: The config data to process.

        Returns:
            The config data with environment variables expanded.
        """
        if isinstance(data, dict):
            return {key: self._expand_config_data(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self._expand_config_data(item) for item in data]
        if isinstance(data, str):
            return expand_env_vars(data)
        return data

    def _parse_config(self, data: Dict[str, Any], source_path: Path) -> FileConfig:
        """Parse raw config data into a FileConfig object."""
        # Expand environment variables in all string values
        data = self._expand_config_data(data)

        generate_data = data.get("generate", {})
        ai_data = data.get("ai", {})
        templates_data = data.get("templates", {})

        generate_config = GenerateConfig(
            format=generate_data.get("format", "markdown"),
            include_scopes=generate_data.get("include_scopes", True),
            no_merge_commits=generate_data.get("no_merge_commits", False),
            no_prs=generate_data.get("no_prs", False),
            fail_on_empty=generate_data.get("fail_on_empty", False),
            include_types=generate_data.get("include_types", []),
            exclude_scopes=generate_data.get("exclude_scopes", []),
            author_filter=generate_data.get("author_filter"),
            include_paths=generate_data.get("include_paths", []),
            exclude_paths=generate_data.get("exclude_paths", []),
            section_order=generate_data.get("section_order", []),
        )

        ai_config = AIConfig(
            enabled=ai_data.get("enabled", False),
            provider=ai_data.get("provider", "openrouter"),
            openai_model=ai_data.get("openai_model", "gpt-4o-mini"),
            openrouter_model=ai_data.get(
                "openrouter_model", "meta-llama/llama-3.3-70b-instruct:free"
            ),
            include_diffs=ai_data.get("include_diffs", False),
            domain_scope=ai_data.get("domain_scope"),
            expert_roles=ai_data.get("expert_roles", []),
            rag_backend=ai_data.get("rag_backend", "simple"),
        )

        template_config = self._parse_templates(templates_data, source_path)

        return FileConfig(
            generate=generate_config,
            ai=ai_config,
            templates=template_config,
            _source_path=source_path,
        )

    def _parse_templates(self, data: Dict[str, Any], source_path: Path) -> TemplateConfig:
        """Parse template configuration data.

        Template paths are resolved relative to the config file's directory.
        """
        config_dir = source_path.parent

        def resolve_path(value: Optional[str]) -> Optional[Path]:
            if not value:
                return None
            path = Path(value)
            if not path.is_absolute():
                path = config_dir / path
            return path.resolve()

        return TemplateConfig(
            markdown=resolve_path(data.get("markdown")),
            html=resolve_path(data.get("html")),
            text=resolve_path(data.get("text")),
            json=resolve_path(data.get("json")),
            yaml=resolve_path(data.get("yaml")),
        )


def load_config(
    repo_path: Optional[Path] = None, config_file: Optional[Path] = None
) -> FileConfig:
    """Convenience function to load configuration from a repository.

    Args:
        repo_path: Path to the repository root. Defaults to current directory.
        config_file: Explicit path to a config file. If provided, this file
            will be used instead of searching for config files in repo_path.

    Returns:
        FileConfig with parsed settings.
    """
    loader = ConfigLoader(repo_path, config_file=config_file)
    return loader.load()


__all__ = [
    "DEFAULT_TEMPLATE_DIR",
    "ENV_VAR_PATTERN",
    "expand_env_vars",
    "GeneratorConfig",
    "GenerateConfig",
    "AIConfig",
    "TemplateConfig",
    "FileConfig",
    "ConfigLoader",
    "load_config",
    "CONFIG_FILES",
]
