"""
Tool: Service Registry

Loads services.yaml and provides the agent with a tool to look up
service metadata (log groups, owners, dependencies) by alarm name
or service name.
"""

import json
import logging
import os
from typing import Optional

import yaml
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── Module-level registry (loaded once) ────────────────────────────────

_registry_data: Optional[dict] = None
_alarm_to_service: Optional[dict] = None


def _load_registry(path: str = None) -> dict:
    """Load and cache the services.yaml file."""
    global _registry_data, _alarm_to_service

    if _registry_data is not None:
        return _registry_data

    if path is None:
        from framework.core.config import get_services_path
        path = get_services_path()

    if not os.path.exists(path):
        logger.warning("Service registry not found at %s", path)
        _registry_data = {}
        _alarm_to_service = {}
        return _registry_data

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    _registry_data = data.get("services", {})

    # Build reverse index: alarm_name → service_name
    _alarm_to_service = {}
    for svc_name, svc_info in _registry_data.items():
        for alarm in svc_info.get("alarms", []):
            _alarm_to_service[alarm.lower()] = svc_name

    logger.info(
        "Service registry loaded: %d services, %d alarms mapped",
        len(_registry_data),
        len(_alarm_to_service),
    )
    return _registry_data


def lookup_by_alarm(alarm_name: str) -> Optional[dict]:
    """Find service info by alarm name."""
    _load_registry()
    svc_name = _alarm_to_service.get(alarm_name.lower())
    if svc_name and svc_name in _registry_data:
        info = dict(_registry_data[svc_name])
        info["service_name"] = svc_name
        return info
    return None


def lookup_by_service(service_name: str) -> Optional[dict]:
    """Find service info by service name."""
    _load_registry()
    # Try exact match first
    if service_name in _registry_data:
        info = dict(_registry_data[service_name])
        info["service_name"] = service_name
        return info
    # Try partial match
    for svc_name, svc_info in _registry_data.items():
        if service_name.lower() in svc_name.lower():
            info = dict(svc_info)
            info["service_name"] = svc_name
            return info
    return None


@tool
def fetch_service_info(alarm_name_or_service: str) -> str:
    """
    Look up service information from the registry by alarm name or service name.

    Use this tool to find log groups, owner teams, dependencies, and runbook
    links for a given AWS alarm or service.

    Args:
        alarm_name_or_service: Either an alarm name (e.g. 'qp-booking-service-common-error')
                               or a service name (e.g. 'qp-booking-service').

    Returns:
        A JSON string with the service details, or an error message if not found.
    """
    _load_registry()

    # Try alarm lookup first, then service lookup
    result = lookup_by_alarm(alarm_name_or_service)
    if not result:
        result = lookup_by_service(alarm_name_or_service)

    if result:
        logger.info("Registry hit for '%s' → service '%s'", alarm_name_or_service, result["service_name"])
        return json.dumps(result, indent=2)

    # Not found — return helpful message
    available = list(_registry_data.keys()) if _registry_data else []
    msg = {
        "error": f"No service or alarm found matching '{alarm_name_or_service}'",
        "available_services": available,
        "hint": "Try using the exact alarm name from the email, or a service name from the registry.",
    }
    logger.warning("Registry miss for '%s'", alarm_name_or_service)
    return json.dumps(msg, indent=2)
