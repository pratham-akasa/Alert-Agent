"""
Persistent Memory — JSON-backed key-value store + conversation log.

Provides the agent with cross-session state that survives restarts.
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Memory:
    """
    Generic agent memory backed by a JSON file.

    Stores:
      - facts: key-value pairs the agent explicitly saves
      - history: chronological list of event summaries
      - corrections: per-alarm corrections from users (learning memory)
    """

    def __init__(self, filepath: str = "memory.json"):
        self.filepath = filepath
        self.facts: dict[str, Any] = {}
        self.history: list[dict] = []
        self.corrections: dict[str, list[dict]] = {}
        self._load()

    # ── Public API ─────────────────────────────────────────────────────

    def store(self, key: str, value: Any) -> None:
        """Store a fact in memory."""
        self.facts[key] = value
        logger.debug("Memory.store: %s = %s", key, value)
        self._save()

    def recall(self, key: str, default: Any = None) -> Any:
        """Recall a fact from memory."""
        return self.facts.get(key, default)

    def add_event(self, summary: str, metadata: Optional[dict] = None) -> None:
        """Append an event to history."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
        }
        if metadata:
            entry["metadata"] = metadata
        self.history.append(entry)
        # Keep last 200 events to avoid unbounded growth
        if len(self.history) > 200:
            self.history = self.history[-200:]
        self._save()

    # ── Corrections API ─────────────────────────────────────────────────

    def add_correction(self, alarm_name: str, correction: str) -> None:
        """Store a user correction for a specific alarm."""
        key = alarm_name.lower().strip()
        if key not in self.corrections:
            self.corrections[key] = []
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correction": correction,
        }
        self.corrections[key].append(entry)
        # Keep last 10 corrections per alarm
        if len(self.corrections[key]) > 10:
            self.corrections[key] = self.corrections[key][-10:]
        logger.info("Correction stored for alarm '%s': %s", alarm_name, correction[:100])
        self._save()

    def get_corrections(self, alarm_name: str) -> list[dict]:
        """Get all corrections for a specific alarm."""
        return self.corrections.get(alarm_name.lower().strip(), [])

    def get_all_corrections(self) -> dict[str, list[dict]]:
        """Get all corrections across all alarms."""
        return dict(self.corrections)

    # ── Context summary ────────────────────────────────────────────────

    def get_context_summary(self, max_events: int = 10) -> str:
        """
        Return a human-readable summary suitable for injecting into
        the agent's system prompt as background context.
        """
        lines = []
        if self.facts:
            lines.append("## Known Facts")
            for k, v in self.facts.items():
                lines.append(f"- {k}: {v}")

        if self.corrections:
            lines.append("\n## Learned Corrections")
            lines.append("These are corrections from past investigations. ALWAYS apply them.")
            for alarm, entries in self.corrections.items():
                latest = entries[-1]  # most recent correction
                lines.append(f"- **{alarm}**: {latest['correction']}")

        if self.history:
            recent = self.history[-max_events:]
            lines.append(f"\n## Recent Events (last {len(recent)})")
            for evt in recent:
                lines.append(f"- [{evt['timestamp']}] {evt['summary']}")

        return "\n".join(lines) if lines else "No prior context."

    def clear(self) -> None:
        """Reset all memory."""
        self.facts = {}
        self.history = []
        self.corrections = {}
        self._save()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                self.facts = data.get("facts", {})
                self.history = data.get("history", [])
                self.corrections = data.get("corrections", {})
                logger.info(
                    "Memory loaded from %s (%d facts, %d events, %d alarm corrections)",
                    self.filepath, len(self.facts), len(self.history), len(self.corrections),
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Corrupt memory file, starting fresh: %s", e)
                self.facts = {}
                self.history = []
                self.corrections = {}

    def _save(self) -> None:
        with open(self.filepath, "w") as f:
            json.dump(
                {"facts": self.facts, "history": self.history, "corrections": self.corrections},
                f, indent=2,
            )
