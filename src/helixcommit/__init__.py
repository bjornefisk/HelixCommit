"""Initialize the helixcommit package."""

from .bitbucket_client import (
    BitbucketApiError,
    BitbucketClient,
    BitbucketRateLimitError,
    BitbucketSettings,
)
from .config import TemplateConfig
from .template import (
    TemplateEngine,
    changelog_to_context,
    detect_format_from_template,
    render_template,
)

__all__ = [
    "__version__",
    "BitbucketApiError",
    "BitbucketClient",
    "BitbucketRateLimitError",
    "BitbucketSettings",
    "TemplateConfig",
    "TemplateEngine",
    "changelog_to_context",
    "detect_format_from_template",
    "render_template",
]

__version__ = "0.1.0"
