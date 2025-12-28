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
from .ui import (
    get_console,
    get_err_console,
    set_theme,
    DARK_THEME,
    LIGHT_THEME,
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
    # UI exports
    "get_console",
    "get_err_console",
    "set_theme",
    "DARK_THEME",
    "LIGHT_THEME",
]

__version__ = "1.2.4"
