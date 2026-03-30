"""
Config loader — reads config.yaml and provides typed access to settings.
Provides centralized path resolution for repo-root config files.
"""

import os
import yaml
from typing import Any, Dict


def get_repo_root() -> str:
    """
    Get the repository root directory.
    
    This function works from any file in the repository by finding the directory
    that contains both config.yaml and main.py (which should be the repo root).
    """
    # Start from this file's directory (framework/core/)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Go up directories until we find the repo root
    while current_dir != os.path.dirname(current_dir):  # Stop at filesystem root
        # Check if this directory contains the expected root files
        config_file = os.path.join(current_dir, "config.yaml")
        main_file = os.path.join(current_dir, "main.py")
        
        if os.path.exists(config_file) and os.path.exists(main_file):
            return current_dir
            
        # Go up one level
        current_dir = os.path.dirname(current_dir)
    
    # Fallback: assume we're in framework/core/ and go up 2 levels
    fallback_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return fallback_root


def get_config_path() -> str:
    """Get the full path to config.yaml at repo root."""
    return os.path.join(get_repo_root(), "config.yaml")


def get_services_path() -> str:
    """Get the full path to services.yaml at repo root."""
    return os.path.join(get_repo_root(), "services.yaml")


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load and parse config.yaml.
    
    Args:
        config_path: Optional custom path to config file. If None, uses repo root config.yaml.
        
    Returns:
        Parsed YAML data as dictionary.
        
    Raises:
        FileNotFoundError: If config file doesn't exist.
    """
    if config_path is None:
        config_path = get_config_path()
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at: {config_path}")
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_services(services_path: str = None) -> Dict[str, Any]:
    """
    Load and parse services.yaml.
    
    Args:
        services_path: Optional custom path to services file. If None, uses repo root services.yaml.
        
    Returns:
        Parsed YAML data as dictionary.
        
    Raises:
        FileNotFoundError: If services file doesn't exist.
    """
    if services_path is None:
        services_path = get_services_path()
    
    if not os.path.exists(services_path):
        raise FileNotFoundError(f"Services file not found at: {services_path}")
    
    with open(services_path, "r") as f:
        return yaml.safe_load(f)


class Config:
    """Load and access config.yaml settings."""

    def __init__(self, config_path: str = None):
        self._data = load_config(config_path)

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
    def bedrock_model_id(self) -> str:
        return self.get("bedrock.model_id", "anthropic.claude-3-haiku-20240307-v1:0")

    @property
    def bedrock_region(self) -> str:
        return self.get("bedrock.region", self.get("aws.region", "ap-south-1"))

    @property
    def bedrock_access_key_id(self) -> str:
        return self.get("bedrock.access_key_id", "")

    @property
    def bedrock_secret_access_key(self) -> str:
        return self.get("bedrock.secret_access_key", "")

    @property
    def bedrock_session_token(self) -> str:
        return self.get("bedrock.session_token", "")

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
        """Get path to services.yaml, with fallback to default location."""
        custom_path = self.get("agent.services_registry")
        if custom_path:
            return custom_path
        return get_services_path()

    @property
    def teams_config(self) -> dict:
        return self._data.get("teams", {})
