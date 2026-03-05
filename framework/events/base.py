"""
Event system — base classes for events and event sources.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class Event:
    """A single event that triggers the agent."""

    source: str                           # e.g. "email", "webhook", "manual"
    event_type: str                       # e.g. "aws_alarm", "sns_notification"
    payload: dict[str, Any]               # raw data
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def summary(self) -> str:
        """One-line human-readable summary."""
        return f"[{self.source}/{self.event_type}] at {self.timestamp.isoformat()}"


class EventSource(ABC):
    """
    Abstract base class for event sources.

    Subclasses implement `start()` which should run in an asyncio loop
    and call `self._emit(event)` whenever a new event arrives.
    """

    def __init__(self):
        self._callback: Callable[[Event], Any] | None = None

    def on_event(self, callback: Callable[[Event], Any]) -> None:
        """Register a callback that receives each Event."""
        self._callback = callback

    def _emit(self, event: Event) -> None:
        """Push an event to the registered callback."""
        if self._callback:
            self._callback(event)

    @abstractmethod
    async def start(self) -> None:
        """Start listening / polling for events. Runs forever."""
        ...

    async def stop(self) -> None:
        """Optional cleanup hook."""
        pass
