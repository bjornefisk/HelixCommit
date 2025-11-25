from pathlib import Path

from helixcommit.config import GeneratorConfig


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
