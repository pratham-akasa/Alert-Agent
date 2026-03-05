"""
Config loader — reads config.yaml and provides typed access to settings.
"""

import os
import yaml
from typing import Any


class Config:
    """Load and access config.yaml settings."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config.yaml",
            )
        with open(config_path, "r") as f:
            self._data = yaml.safe_load(f)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Access nested config via dot notation, e.g. 'ollama.model'."""
        keys = dotted_key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    # ── Convenience properties ─────────────────────────────────────────

    @property
    def ollama_base_url(self) -> str:
        return self.get("ollama.base_url", "http://localhost:11434")

    @property
    def ollama_model(self) -> str:
        return self.get("ollama.model", "qwen2.5:7b")

    @property
    def email_config(self) -> dict:
        return self._data.get("email", {})

    @property
    def aws_config(self) -> dict:
        return self._data.get("aws", {})

    @property
    def log_groups(self) -> dict:
        return self._data.get("log_groups", {})

    @property
    def agent_config(self) -> dict:
        return self._data.get("agent", {})

    @property
    def services_registry_path(self) -> str:
        return self.get(
            "agent.services_registry",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "services.yaml",
            ),
        )

    @property
    def teams_config(self) -> dict:
        return self._data.get("teams", {})
