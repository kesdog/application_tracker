"""Embed search, async crawling and structured extraction in any Python application."""

from .core import WebToolbox
from .jobs import JobHandle
from .settings import Settings

__all__ = ["WebToolbox", "Settings", "JobHandle"]
