"""
Persistent Memory with S3 backend for Lambda deployment.

Provides the agent with cross-session state that survives Lambda cold starts.
Memory is stored in S3 instead of local filesystem.
"""

import json
import os
import logging
import boto3
from datetime import datetime, timezone
from typing import Any, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class Memory:
    """
    Generic agent memory backed by S3.

    Stores:
      - facts: key-value pairs the agent explicitly saves
      - history: chronological list of event summaries
      - corrections: per-alarm corrections from users (learning memory)
    """

    def __init__(self, filepath: str = "memory.json", s3_bucket: Optional[str] = None, s3_key: Optional[str] = None):
        self.filepath = filepath
        self.s3_bucket = s3_bucket
        self.s3_key = s3_key or filepath
        self.s3_client = boto3.client('s3') if s3_bucket else None
        
        self.facts: dict[str, Any] = {}
        self.history: list[dict] = []
        self.corrections: dict[str, list[dict]] = {}
        
        # Load from S3 if configured, otherwise local file
        if self.s3_bucket:
            self._load_from_s3()
        else:
            self._load_from_file()

    @classmethod
    def from_s3(cls, bucket: str, key: str = "memory.json") -> 'Memory':
        """
        Factory method to create Memory with S3 backend.
        
        Args:
            bucket: S3 bucket name
            key: S3 object key (default: memory.json)
            
        Returns:
            Memory instance configured for S3
        """
        return cls(filepath=key, s3_bucket=bucket, s3_key=key)

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

    # ── Persistence (S3) ───────────────────────────────────────────────

    def _load_from_s3(self) -> None:
        """Load memory from S3."""
        if not self.s3_client or not self.s3_bucket:
            logger.warning("S3 not configured, skipping load")
            return
        
        try:
            logger.info(f"Loading memory from s3://{self.s3_bucket}/{self.s3_key}")
            response = self.s3_client.get_object(Bucket=self.s3_bucket, Key=self.s3_key)
            data = json.loads(response['Body'].read().decode('utf-8'))
            
            self.facts = data.get("facts", {})
            self.history = data.get("history", [])
            self.corrections = data.get("corrections", {})
            
            logger.info(
                "Memory loaded from S3 (%d facts, %d events, %d alarm corrections)",
                len(self.facts), len(self.history), len(self.corrections),
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info("No existing memory in S3, starting fresh")
                self.facts = {}
                self.history = []
                self.corrections = {}
            else:
                logger.error(f"Error loading memory from S3: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error loading memory from S3: {e}")
            raise

    def _save_to_s3(self) -> None:
        """Save memory to S3."""
        if not self.s3_client or not self.s3_bucket:
            logger.warning("S3 not configured, skipping save")
            return
        
        try:
            data = {
                "facts": self.facts,
                "history": self.history,
                "corrections": self.corrections,
            }
            
            logger.info(f"Saving memory to s3://{self.s3_bucket}/{self.s3_key}")
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=self.s3_key,
                Body=json.dumps(data, indent=2).encode('utf-8'),
                ContentType='application/json',
            )
            logger.info("Memory saved to S3 successfully")
        except Exception as e:
            logger.error(f"Error saving memory to S3: {e}")
            raise

    def save_to_s3(self) -> None:
        """Public method to explicitly save to S3 (called by Lambda handler)."""
        self._save_to_s3()

    # ── Persistence (Local File - fallback) ───────────────────────────

    def _load_from_file(self) -> None:
        """Load memory from local file (fallback for local testing)."""
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
        else:
            logger.info("No existing memory file, starting fresh")

    def _save_to_file(self) -> None:
        """Save memory to local file (fallback for local testing)."""
        # Use /tmp/ in Lambda environment (only writable directory)
        filepath = self.filepath
        if not filepath.startswith('/tmp/') and os.environ.get('AWS_EXECUTION_ENV'):
            filepath = f'/tmp/{os.path.basename(self.filepath)}'
        
        with open(filepath, "w") as f:
            json.dump(
                {"facts": self.facts, "history": self.history, "corrections": self.corrections},
                f, indent=2,
            )

    def _save(self) -> None:
        """Save memory (routes to S3 or file based on configuration)."""
        if self.s3_bucket:
            self._save_to_s3()
        else:
            self._save_to_file()
