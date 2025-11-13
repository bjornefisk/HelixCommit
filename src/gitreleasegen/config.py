"""Configuration helpers for GitReleaseGenerator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

DEFAULT_TEMPLATE_DIR = Path(__file__).with_suffix("").parent / "formatters"


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
    template_path: Optional[Path] = None
    sections_order: Sequence[str] = field(default_factory=list)


__all__ = ["DEFAULT_TEMPLATE_DIR", "GeneratorConfig"]
