import os
from pathlib import Path

import pytest

from helixcommit.config import (
    AIConfig,
    ConfigLoader,
    FileConfig,
    GenerateConfig,
    GeneratorConfig,
    TemplateConfig,
    expand_env_vars,
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


# --- TemplateConfig tests ---


def test_template_config_defaults():
    """TemplateConfig has None for all formats by default."""
    config = TemplateConfig()
    assert config.markdown is None
    assert config.html is None
    assert config.text is None
    assert config.json is None
    assert config.yaml is None


def test_template_config_custom():
    """TemplateConfig accepts custom paths."""
    config = TemplateConfig(
        markdown=Path("/custom/markdown.j2"),
        html=Path("/custom/html.j2"),
    )
    assert config.markdown == Path("/custom/markdown.j2")
    assert config.html == Path("/custom/html.j2")
    assert config.text is None


def test_template_config_get_template_for_format():
    """get_template_for_format returns the correct template path."""
    config = TemplateConfig(
        markdown=Path("/custom/md.j2"),
        html=Path("/custom/html.j2"),
    )
    assert config.get_template_for_format("markdown") == Path("/custom/md.j2")
    assert config.get_template_for_format("html") == Path("/custom/html.j2")
    assert config.get_template_for_format("text") is None
    assert config.get_template_for_format("unknown") is None


def test_file_config_includes_templates():
    """FileConfig includes TemplateConfig."""
    config = FileConfig()
    assert isinstance(config.templates, TemplateConfig)


def test_config_loader_loads_templates_toml(tmp_path):
    """ConfigLoader correctly parses template paths from TOML."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    md_template = templates_dir / "changelog.md.j2"
    md_template.write_text("# Test")

    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[templates]
markdown = "templates/changelog.md.j2"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    # Template path should be resolved relative to config file
    assert config.templates.markdown == md_template.resolve()
    assert config.templates.html is None


def test_config_loader_loads_templates_yaml(tmp_path):
    """ConfigLoader correctly parses template paths from YAML."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    html_template = templates_dir / "changelog.html.j2"
    html_template.write_text("<h1>Test</h1>")

    config_file = tmp_path / ".helixcommit.yaml"
    config_file.write_text("""
templates:
  html: templates/changelog.html.j2
  text: templates/changelog.txt.j2
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.templates.html == (templates_dir / "changelog.html.j2").resolve()
    assert config.templates.text == (templates_dir / "changelog.txt.j2").resolve()
    assert config.templates.markdown is None


def test_config_loader_templates_absolute_path(tmp_path):
    """ConfigLoader handles absolute template paths."""
    abs_path = tmp_path / "abs" / "template.md.j2"
    abs_path.parent.mkdir()
    abs_path.write_text("# Absolute")

    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text(f"""
[templates]
markdown = "{abs_path}"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.templates.markdown == abs_path.resolve()


# --- Environment Variable Expansion tests ---


def test_expand_env_vars_basic(monkeypatch):
    """expand_env_vars expands basic ${VAR} syntax."""
    monkeypatch.setenv("TEST_VAR", "hello")
    assert expand_env_vars("${TEST_VAR}") == "hello"
    assert expand_env_vars("prefix-${TEST_VAR}-suffix") == "prefix-hello-suffix"


def test_expand_env_vars_with_default(monkeypatch):
    """expand_env_vars supports ${VAR:-default} syntax."""
    # When var is set, use its value
    monkeypatch.setenv("TEST_VAR", "actual")
    assert expand_env_vars("${TEST_VAR:-fallback}") == "actual"

    # When var is not set, use default
    monkeypatch.delenv("TEST_VAR", raising=False)
    assert expand_env_vars("${TEST_VAR:-fallback}") == "fallback"


def test_expand_env_vars_empty_default(monkeypatch):
    """expand_env_vars handles empty default values."""
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert expand_env_vars("${MISSING_VAR:-}") == ""


def test_expand_env_vars_missing_var_no_default(monkeypatch):
    """expand_env_vars keeps original reference if var not set and no default."""
    monkeypatch.delenv("UNDEFINED_VAR", raising=False)
    assert expand_env_vars("${UNDEFINED_VAR}") == "${UNDEFINED_VAR}"


def test_expand_env_vars_multiple(monkeypatch):
    """expand_env_vars expands multiple variables in one string."""
    monkeypatch.setenv("VAR1", "one")
    monkeypatch.setenv("VAR2", "two")
    assert expand_env_vars("${VAR1} and ${VAR2}") == "one and two"


def test_expand_env_vars_no_vars():
    """expand_env_vars returns string unchanged if no env vars."""
    assert expand_env_vars("plain string") == "plain string"
    assert expand_env_vars("") == ""


def test_config_loader_env_var_expansion_toml(tmp_path, monkeypatch):
    """ConfigLoader expands env vars in TOML config values."""
    monkeypatch.setenv("HELIX_FORMAT", "html")
    monkeypatch.setenv("HELIX_DOMAIN", "conservation")

    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[generate]
format = "${HELIX_FORMAT}"

[ai]
enabled = true
domain_scope = "${HELIX_DOMAIN}"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.generate.format == "html"
    assert config.ai.domain_scope == "conservation"


def test_config_loader_env_var_expansion_yaml(tmp_path, monkeypatch):
    """ConfigLoader expands env vars in YAML config values."""
    monkeypatch.setenv("HELIX_PROVIDER", "openai")
    monkeypatch.setenv("HELIX_MODEL", "gpt-4o")

    config_file = tmp_path / ".helixcommit.yaml"
    config_file.write_text("""
ai:
  enabled: true
  provider: "${HELIX_PROVIDER}"
  openai_model: "${HELIX_MODEL}"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.ai.provider == "openai"
    assert config.ai.openai_model == "gpt-4o"


def test_config_loader_env_var_with_default(tmp_path, monkeypatch):
    """ConfigLoader uses default values when env vars not set."""
    # Ensure variable is not set
    monkeypatch.delenv("UNDEFINED_MODEL", raising=False)

    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[ai]
enabled = true
openai_model = "${UNDEFINED_MODEL:-gpt-4o-mini}"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.ai.openai_model == "gpt-4o-mini"


def test_config_loader_env_var_in_list(tmp_path, monkeypatch):
    """ConfigLoader expands env vars in list values."""
    monkeypatch.setenv("ROLE1", "Product Manager")
    monkeypatch.setenv("ROLE2", "Tech Lead")

    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[ai]
enabled = true
expert_roles = ["${ROLE1}", "${ROLE2}", "QA Engineer"]
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.ai.expert_roles == ["Product Manager", "Tech Lead", "QA Engineer"]


def test_config_loader_env_var_in_template_path(tmp_path, monkeypatch):
    """ConfigLoader expands env vars in template paths."""
    templates_dir = tmp_path / "custom-templates"
    templates_dir.mkdir()
    md_template = templates_dir / "release.md.j2"
    md_template.write_text("# Release Notes")

    monkeypatch.setenv("TEMPLATE_DIR", "custom-templates")

    config_file = tmp_path / ".helixcommit.toml"
    config_file.write_text("""
[templates]
markdown = "${TEMPLATE_DIR}/release.md.j2"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.templates.markdown == md_template.resolve()


def test_config_loader_mixed_env_vars_and_literals(tmp_path, monkeypatch):
    """ConfigLoader handles mix of env vars and literal values."""
    monkeypatch.setenv("APP_NAME", "myapp")

    config_file = tmp_path / ".helixcommit.yaml"
    config_file.write_text("""
ai:
  enabled: true
  domain_scope: "Release notes for ${APP_NAME} project"
""")

    loader = ConfigLoader(tmp_path)
    config = loader.load()

    assert config.ai.domain_scope == "Release notes for myapp project"


# --- Explicit config file path tests ---


def test_config_loader_explicit_config_file(tmp_path):
    """ConfigLoader loads from explicit config file path."""
    custom_config = tmp_path / "custom" / "my-config.toml"
    custom_config.parent.mkdir(parents=True)
    custom_config.write_text("""
[generate]
format = "html"

[ai]
enabled = true
provider = "openai"
""")

    loader = ConfigLoader(tmp_path, config_file=custom_config)
    config = loader.load()

    assert config.source_path == custom_config
    assert config.generate.format == "html"
    assert config.ai.enabled is True
    assert config.ai.provider == "openai"


def test_config_loader_explicit_config_file_yaml(tmp_path):
    """ConfigLoader loads from explicit YAML config file path."""
    custom_config = tmp_path / "configs" / "project.yaml"
    custom_config.parent.mkdir(parents=True)
    custom_config.write_text("""
generate:
  format: text
  no_merge_commits: true

ai:
  enabled: true
  domain_scope: custom domain
""")

    loader = ConfigLoader(tmp_path, config_file=custom_config)
    config = loader.load()

    assert config.source_path == custom_config
    assert config.generate.format == "text"
    assert config.generate.no_merge_commits is True
    assert config.ai.domain_scope == "custom domain"


def test_config_loader_explicit_config_overrides_default(tmp_path):
    """Explicit config file takes precedence over default config in repo."""
    # Create default config in repo
    default_config = tmp_path / ".helixcommit.toml"
    default_config.write_text("""
[generate]
format = "markdown"
""")

    # Create custom config elsewhere
    custom_config = tmp_path / "custom" / "config.toml"
    custom_config.parent.mkdir(parents=True)
    custom_config.write_text("""
[generate]
format = "json"
""")

    # Without explicit config, uses default
    loader_default = ConfigLoader(tmp_path)
    config_default = loader_default.load()
    assert config_default.generate.format == "markdown"

    # With explicit config, uses custom
    loader_custom = ConfigLoader(tmp_path, config_file=custom_config)
    config_custom = loader_custom.load()
    assert config_custom.generate.format == "json"


def test_config_loader_explicit_config_not_found(tmp_path):
    """ConfigLoader returns defaults if explicit config file doesn't exist."""
    nonexistent = tmp_path / "nonexistent.toml"

    loader = ConfigLoader(tmp_path, config_file=nonexistent)
    config = loader.load()

    # Should return defaults since file doesn't exist
    assert config.source_path is None
    assert config.generate.format == "markdown"
    assert config.ai.enabled is False


def test_config_loader_explicit_config_templates_relative(tmp_path):
    """Template paths in explicit config are relative to config file location."""
    # Create custom config in subdirectory
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    # Create templates relative to config location
    templates_dir = config_dir / "templates"
    templates_dir.mkdir()
    template_file = templates_dir / "custom.md.j2"
    template_file.write_text("# Custom Template")

    custom_config = config_dir / "helixcommit.toml"
    custom_config.write_text("""
[templates]
markdown = "templates/custom.md.j2"
""")

    loader = ConfigLoader(tmp_path, config_file=custom_config)
    config = loader.load()

    # Template path should be resolved relative to config file location
    assert config.templates.markdown == template_file.resolve()


def test_load_config_with_explicit_file(tmp_path):
    """load_config convenience function accepts config_file parameter."""
    custom_config = tmp_path / "my-config.yaml"
    custom_config.write_text("""
ai:
  enabled: true
  provider: openrouter
""")

    config = load_config(tmp_path, config_file=custom_config)

    assert config.ai.enabled is True
    assert config.ai.provider == "openrouter"


def test_load_config_explicit_file_not_found(tmp_path):
    """load_config returns defaults if explicit config file doesn't exist."""
    nonexistent = tmp_path / "missing.toml"

    config = load_config(tmp_path, config_file=nonexistent)

    assert config.source_path is None
    assert config.generate.format == "markdown"
