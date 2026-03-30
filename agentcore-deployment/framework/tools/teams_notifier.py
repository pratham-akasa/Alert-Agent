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
    url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    if url:
        return url
    try:
        from framework.core.config import Config
        config = Config()
        return config.teams_config.get("webhook_url", "")
    except Exception:
        return ""


def _infer_severity(summary: str, alarm_name: str) -> str:
    """
    Infer severity from the investigation summary and alarm name.

    Rules (in priority order):
    - 'Critical' if summary mentions outage / service down / 500 errors / fatal
    - 'Low'      if alarm resolved / OK state / no errors found
    - 'Medium'   if threshold crossed but no log evidence of errors
    - 'High'     default — alarm fired with errors present
    """
    text = (summary + " " + alarm_name).lower()

    critical_keywords = ["outage", "down", "unavailable", "data loss", "500", "critical", "fatal", "crash"]
    low_keywords = ["ok", "resolved", "no errors found", "no error"]
    medium_keywords = ["no errors", "event_count: 0", 'event_count":0', "threshold crossed"]

    if any(k in text for k in critical_keywords):
        return "Critical"
    if any(k in text for k in low_keywords):
        return "Low"
    if any(k in text for k in medium_keywords):
        return "Medium"
    return "High"


def _build_adaptive_card(
    alarm_name: str,
    summary: str,
    severity: str,
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

    card_body.append({"type": "TextBlock", "text": "---"})
    card_body.append({"type": "TextBlock", "text": summary, "wrap": True})

    return {
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


@tool
def notify_teams(
    summary: str,
    alarm_name: str = "Unknown Alarm",
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
        owner_team: The team responsible for this service (from service registry).
        log_group: The CloudWatch log group that was investigated.

    Returns:
        A JSON string confirming delivery or explaining the error.
    """
    # Auto-infer severity from the summary content — don't rely on LLM to pass it correctly
    severity = _infer_severity(summary, alarm_name)
    logger.info("Auto-inferred severity for '%s': %s", alarm_name, severity)

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
                "severity": severity,
                "message": "Investigation summary posted to Teams successfully.",
            }
            logger.info("Teams notification sent for alarm: %s (severity=%s)", alarm_name, severity)
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
