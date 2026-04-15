"""GitHub backup package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("github_backup")
except PackageNotFoundError:
    __version__ = "0.0.0"
