"""Embed search, async crawling and structured extraction in any Python application."""

from .core import WebToolbox
from .jobs import JobHandle
from .settings import Settings
from .ranking import merge_and_rank, rank_contact, shortlist_summary

__all__ = ["WebToolbox", "Settings", "JobHandle", "rank_contact", "merge_and_rank", "shortlist_summary", "KeywordProfile", "load_profile", "EmployerContext"]

# Portable profile and employer evidence types for consumers.
from .profiles import KeywordProfile, load_profile
from .identity import EmployerContext
