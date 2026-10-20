"""Informational call correlation. Client labels never grant authority."""
from contextvars import ContextVar

current_call = ContextVar('tracker_agent_call', default=None)
