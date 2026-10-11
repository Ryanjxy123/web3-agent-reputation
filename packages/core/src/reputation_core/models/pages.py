"""Bounded operator-list responses; cursors identify the last immutable row."""

from uuid import UUID

from .api import AgentView
from .base import Model
from .domain import AgentSnapshot
from .reporting import ReportView


class AgentPage(Model):
    items: tuple[AgentView, ...]
    next_cursor: UUID | None = None


class SnapshotPage(Model):
    items: tuple[AgentSnapshot, ...]
    next_cursor: UUID | None = None


class ReportPage(Model):
    items: tuple[ReportView, ...]
    next_cursor: UUID | None = None
