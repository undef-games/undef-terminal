from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("undef-terminal-cloudflare")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .config import CloudflareConfig

__all__ = ["CloudflareConfig", "__version__"]
