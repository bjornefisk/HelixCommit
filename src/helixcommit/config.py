"""Configuration helpers for HelixCommit."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_TEMPLATE_DIR = Path(__file__).with_suffix("").parent / "formatters"

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


@dataclass
class AIConfig:
    """Configuration options for AI features."""

    enabled: bool = False
    provider: str = "openrouter"
    openai_model: str = "gpt-4o-mini"
    openrouter_model: str = "x-ai/grok-4.1-fast:free"
    include_diffs: bool = False
    domain_scope: Optional[str] = None
    expert_roles: List[str] = field(default_factory=list)
    rag_backend: str = "simple"


@dataclass
class FileConfig:
    """Parsed configuration from a config file."""

    generate: GenerateConfig = field(default_factory=GenerateConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    _source_path: Optional[Path] = None

    @property
    def source_path(self) -> Optional[Path]:
        """Return the path to the config file that was loaded."""
        return self._source_path


class ConfigLoader:
    """Loads configuration from .helixcommit.toml or .helixcommit.yaml files."""

    def __init__(self, repo_path: Optional[Path] = None) -> None:
        """Initialize the config loader.

        Args:
            repo_path: Path to the repository root. Defaults to current directory.
        """
        self.repo_path = (repo_path or Path.cwd()).resolve()
        self._config: Optional[FileConfig] = None
        self._loaded = False

    def find_config_file(self) -> Optional[Path]:
        """Find the first config file in the repository root.

        Returns:
            Path to the config file, or None if not found.
        """
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

    def _parse_config(self, data: Dict[str, Any], source_path: Path) -> FileConfig:
        """Parse raw config data into a FileConfig object."""
        generate_data = data.get("generate", {})
        ai_data = data.get("ai", {})

        generate_config = GenerateConfig(
            format=generate_data.get("format", "markdown"),
            include_scopes=generate_data.get("include_scopes", True),
            no_merge_commits=generate_data.get("no_merge_commits", False),
            no_prs=generate_data.get("no_prs", False),
            fail_on_empty=generate_data.get("fail_on_empty", False),
        )

        ai_config = AIConfig(
            enabled=ai_data.get("enabled", False),
            provider=ai_data.get("provider", "openrouter"),
            openai_model=ai_data.get("openai_model", "gpt-4o-mini"),
            openrouter_model=ai_data.get("openrouter_model", "x-ai/grok-4.1-fast:free"),
            include_diffs=ai_data.get("include_diffs", False),
            domain_scope=ai_data.get("domain_scope"),
            expert_roles=ai_data.get("expert_roles", []),
            rag_backend=ai_data.get("rag_backend", "simple"),
        )

        return FileConfig(
            generate=generate_config,
            ai=ai_config,
            _source_path=source_path,
        )


def load_config(repo_path: Optional[Path] = None) -> FileConfig:
    """Convenience function to load configuration from a repository.

    Args:
        repo_path: Path to the repository root. Defaults to current directory.

    Returns:
        FileConfig with parsed settings.
    """
    loader = ConfigLoader(repo_path)
    return loader.load()


__all__ = [
    "DEFAULT_TEMPLATE_DIR",
    "GeneratorConfig",
    "GenerateConfig",
    "AIConfig",
    "FileConfig",
    "ConfigLoader",
    "load_config",
    "CONFIG_FILES",
]
