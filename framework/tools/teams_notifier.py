"""
Tool: MS Teams Notifier

Posts investigation summaries to a Microsoft Teams channel
via an Incoming Webhook using Adaptive Cards.
"""

import json
import logging
import os

import requests
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_webhook_url() -> str:
    """Get the Teams webhook URL from config or environment."""
    # Environment variable takes priority
    url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    if url:
        return url

    # Fall back to config.yaml
    try:
        from framework.config import Config
        config = Config()
        return config.teams_config.get("webhook_url", "")
    except Exception:
        return ""


def _build_adaptive_card(
    alarm_name: str,
    summary: str,
    severity: str = "High",
    owner_team: str = "",
    log_group: str = "",
) -> dict:
    """Build an Adaptive Card payload for Teams."""
    severity_colors = {
        "critical": "attention",
        "high": "attention",
        "medium": "warning",
        "low": "good",
        "info": "accent",
    }
    color = severity_colors.get(severity.lower(), "attention")

    card_body = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": f"🚨 AWS Alert: {alarm_name}",
            "wrap": True,
        },
        {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"Severity: **{severity}**",
                            "color": color,
                            "weight": "Bolder",
                        }
                    ],
                },
            ],
        },
    ]

    if owner_team:
        card_body.append({
            "type": "TextBlock",
            "text": f"👥 **Owner:** {owner_team}",
            "wrap": True,
        })

    if log_group:
        card_body.append({
            "type": "TextBlock",
            "text": f"📋 **Log Group:** `{log_group}`",
            "wrap": True,
        })

    card_body.append({
        "type": "TextBlock",
        "text": "---",
    })

    card_body.append({
        "type": "TextBlock",
        "text": summary,
        "wrap": True,
    })

    # Adaptive Card payload wrapped in the Teams webhook format
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": card_body,
                },
            }
        ],
    }
    return payload


@tool
def notify_teams(
    summary: str,
    alarm_name: str = "Unknown Alarm",
    severity: str = "High",
    owner_team: str = "",
    log_group: str = "",
) -> str:
    """
    Send an investigation summary to a Microsoft Teams channel.

    Use this tool AFTER completing your investigation to notify the team
    about what happened and what action should be taken.

    Args:
        summary: The full investigation summary to post.
        alarm_name: Name of the alarm that triggered (e.g. 'qp-booking-service-common-error').
        severity: Severity level — one of 'Critical', 'High', 'Medium', 'Low', 'Info'.
        owner_team: The team responsible for this service (from service registry).
        log_group: The CloudWatch log group that was investigated.

    Returns:
        A JSON string confirming delivery or explaining the error.
    """
    webhook_url = _get_webhook_url()

    if not webhook_url:
        msg = {
            "status": "skipped",
            "reason": "No Teams webhook URL configured. Set 'teams.webhook_url' in config.yaml or TEAMS_WEBHOOK_URL env var.",
        }
        logger.warning("Teams notification skipped — no webhook URL")
        return json.dumps(msg, indent=2)

    try:
        card = _build_adaptive_card(
            alarm_name=alarm_name,
            summary=summary,
            severity=severity,
            owner_team=owner_team,
            log_group=log_group,
        )

        response = requests.post(
            webhook_url,
            json=card,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code in (200, 202):
            result = {
                "status": "sent",
                "alarm_name": alarm_name,
                "message": "Investigation summary posted to Teams successfully.",
            }
            logger.info("Teams notification sent for alarm: %s", alarm_name)
        else:
            result = {
                "status": "error",
                "http_status": response.status_code,
                "response": response.text[:500],
                "hint": "Check that the webhook URL is valid and the connector is active.",
            }
            logger.error("Teams webhook returned %d: %s", response.status_code, response.text[:200])

        return json.dumps(result, indent=2)

    except requests.RequestException as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "hint": "Network error posting to Teams. Check connectivity and webhook URL.",
        }
        logger.error("Teams notification failed: %s", e)
        return json.dumps(error_result, indent=2)
