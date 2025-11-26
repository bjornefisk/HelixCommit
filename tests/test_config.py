from pathlib import Path

import pytest

from helixcommit.config import (
    AIConfig,
    ConfigLoader,
    FileConfig,
    GenerateConfig,
    GeneratorConfig,
    load_config,
)


def test_generator_config_defaults():
    config = GeneratorConfig()
    assert config.repo_path == Path.cwd()
    assert config.output_format == "markdown"
    assert config.use_llm is False
    assert config.openai_model == "gpt-4o-mini"


def test_generator_config_custom():
    path = Path("/tmp")
    config = GeneratorConfig(repo_path=path, output_format="html", use_llm=True)
    assert config.repo_path == path
    assert config.output_format == "html"
    assert config.use_llm is True


# --- GenerateConfig tests ---


def test_generate_config_defaults():
    config = GenerateConfig()
    assert config.format == "markdown"
    assert config.include_scopes is True
    assert config.no_merge_commits is False
    assert config.no_prs is False
    assert config.fail_on_empty is False


def test_generate_config_custom():
    config = GenerateConfig(
        format="html",
        include_scopes=False,
        no_merge_commits=True,
        no_prs=True,
        fail_on_empty=True,
    )
    assert config.format == "html"
    assert config.include_scopes is False
    assert config.no_merge_commits is True
    assert config.no_prs is True
    assert config.fail_on_empty is True


# --- AIConfig tests ---


def test_ai_config_defaults():
    config = AIConfig()
    assert config.enabled is False
    assert config.provider == "openrouter"
    assert config.openai_model == "gpt-4o-mini"
    assert config.openrouter_model == "x-ai/grok-4.1-fast:free"
    assert config.include_diffs is False
    assert config.domain_scope is None
    assert config.expert_roles == []
    assert config.rag_backend == "simple"


def test_ai_config_custom():
    config = AIConfig(
        enabled=True,
        provider="openai",
        openai_model="gpt-4o",
        openrouter_model="anthropic/claude-3-haiku",
        include_diffs=True,
        domain_scope="software release notes",
        expert_roles=["Product Manager", "Tech Lead"],
        rag_backend="chroma",
    )
    assert config.enabled is True
    assert config.provider == "openai"
    assert config.openai_model == "gpt-4o"
    assert config.openrouter_model == "anthropic/claude-3-haiku"
    assert config.include_diffs is True
    assert config.domain_scope == "software release notes"
    assert config.expert_roles == ["Product Manager", "Tech Lead"]
    assert config.rag_backend == "chroma"


# --- FileConfig tests ---


def test_file_config_defaults():
    config = FileConfig()
    assert isinstance(config.generate, GenerateConfig)
    assert isinstance(config.ai, AIConfig)
    assert config.source_path is None


# --- ConfigLoader tests ---


def test_config_loader_no_file(tmp_path):
    """ConfigLoader returns defaults when no config file exists."""
    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.source_path is None
    assert config.generate.format == "markdown"
    assert config.ai.enabled is False


def test_config_loader_finds_toml(tmp_path):
    """ConfigLoader finds .helixcommit.toml file."""
    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[generate]
format = "html"

[ai]
enabled = true
""")

    loader = ConfigLoader(tmp_path)
    assert loader.find_config_file() == config_file


def test_config_loader_finds_yaml(tmp_path):
    """ConfigLoader finds .helixcommit.yaml file."""
    config_file = tmp_path / ".helixcommit.yaml"
    config_file.write_text("""
generate:
  format: html

ai:
  enabled: true
""")

    loader = ConfigLoader(tmp_path)
    assert loader.find_config_file() == config_file


def test_config_loader_toml_precedence(tmp_path):
    """TOML file takes precedence over YAML when both exist."""
    toml_file = tmp_path / ".helixcommit.toml"
    yaml_file = tmp_path / ".helixcommit.yaml"

    toml_file.write_text('[generate]\nformat = "html"')
    yaml_file.write_text("generate:\n  format: text")

    loader = ConfigLoader(tmp_path)
    assert loader.find_config_file() == toml_file


def test_config_loader_loads_toml(tmp_path):
    """ConfigLoader correctly parses TOML config file."""
    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[generate]
format = "html"
include_scopes = false
no_merge_commits = true
no_prs = true
fail_on_empty = true

[ai]
enabled = true
provider = "openai"
openai_model = "gpt-4o"
openrouter_model = "anthropic/claude-3-haiku"
include_diffs = true
domain_scope = "conservation"
expert_roles = ["Ecologist", "Data Scientist"]
rag_backend = "chroma"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.source_path == config_file
    assert config.generate.format == "html"
    assert config.generate.include_scopes is False
    assert config.generate.no_merge_commits is True
    assert config.generate.no_prs is True
    assert config.generate.fail_on_empty is True

    assert config.ai.enabled is True
    assert config.ai.provider == "openai"
    assert config.ai.openai_model == "gpt-4o"
    assert config.ai.openrouter_model == "anthropic/claude-3-haiku"
    assert config.ai.include_diffs is True
    assert config.ai.domain_scope == "conservation"
    assert config.ai.expert_roles == ["Ecologist", "Data Scientist"]
    assert config.ai.rag_backend == "chroma"


def test_config_loader_loads_yaml(tmp_path):
    """ConfigLoader correctly parses YAML config file."""
    config_file = tmp_path / ".helixcommit.yaml"
    config_file.write_text("""
generate:
  format: text
  include_scopes: false
  no_merge_commits: true

ai:
  enabled: true
  provider: openrouter
  domain_scope: healthcare
  expert_roles:
    - Doctor
    - Nurse
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.source_path == config_file
    assert config.generate.format == "text"
    assert config.generate.include_scopes is False
    assert config.generate.no_merge_commits is True

    assert config.ai.enabled is True
    assert config.ai.provider == "openrouter"
    assert config.ai.domain_scope == "healthcare"
    assert config.ai.expert_roles == ["Doctor", "Nurse"]


def test_config_loader_partial_config(tmp_path):
    """ConfigLoader handles partial config files with missing sections."""
    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[generate]
format = "html"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    # Explicitly set values
    assert config.generate.format == "html"

    # Defaults for missing values
    assert config.generate.include_scopes is True
    assert config.ai.enabled is False
    assert config.ai.provider == "openrouter"


def test_config_loader_invalid_toml(tmp_path):
    """ConfigLoader returns defaults for invalid TOML."""
    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("this is not valid toml [[[")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    # Should fall back to defaults
    assert config.generate.format == "markdown"
    assert config.ai.enabled is False


def test_config_loader_invalid_yaml(tmp_path):
    """ConfigLoader returns defaults for invalid YAML."""
    config_file = tmp_path / ".helixcommit.yaml"
    config_file.write_text("invalid: yaml: content: [")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    # Should fall back to defaults
    assert config.generate.format == "markdown"
    assert config.ai.enabled is False


def test_config_loader_caches_result(tmp_path):
    """ConfigLoader caches the loaded config."""
    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text('[generate]\nformat = "html"')

    loader = ConfigLoader(tmp_path)
    config1 = loader.load()
    config2 = loader.load()

    assert config1 is config2


def test_config_loader_empty_yaml(tmp_path):
    """ConfigLoader handles empty YAML file."""
    config_file = tmp_path / ".helixcommit.yaml"
    config_file.write_text("")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    # Should fall back to defaults
    assert config.generate.format == "markdown"


# --- load_config convenience function tests ---


def test_load_config_function(tmp_path):
    """load_config convenience function works correctly."""
    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text('[ai]\nenabled = true')

    config = load_config(tmp_path)
    assert config.ai.enabled is True


def test_load_config_defaults_to_cwd():
    """load_config uses current directory when no path provided."""
    config = load_config()
    # Should not raise, returns defaults if no config file in cwd
    assert isinstance(config, FileConfig)
