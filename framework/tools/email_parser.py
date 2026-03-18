"""
Tool: AWS Alert Email Parser

Parses raw AWS SNS / CloudWatch alarm email notifications and extracts
structured information the agent can reason about.
"""

import json
import re
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _is_valid_aws_region(region_str: str) -> bool:
    valid_regions = {
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
        'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-central-1',
        'ap-south-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
        'ap-northeast-2', 'ca-central-1', 'sa-east-1'
    }
    return region_str in valid_regions


def _extract_field(text: str, label: str) -> str:
    """
    Extract a field value after a label like '- Timestamp:'.
    Stops at the next ' - ' separator, newline, or end of string.
    Handles both multiline and single-line (HTML-stripped) email bodies.
    """
    pattern = rf'(?:-\s*)?{re.escape(label)}\s*[:\s]\s*(.+?)(?:\s+-\s+[A-Z]|\n|$)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


REGION_MAP = {
    "Asia Pacific (Mumbai)": "ap-south-1",
    "Asia Pacific (Singapore)": "ap-southeast-1",
    "Asia Pacific (Sydney)": "ap-southeast-2",
    "Asia Pacific (Tokyo)": "ap-northeast-1",
    "Asia Pacific (Seoul)": "ap-northeast-2",
    "US East (N. Virginia)": "us-east-1",
    "US East (Ohio)": "us-east-2",
    "US West (N. California)": "us-west-1",
    "US West (Oregon)": "us-west-2",
    "Europe (Ireland)": "eu-west-1",
    "Europe (London)": "eu-west-2",
    "Europe (Paris)": "eu-west-3",
    "Europe (Frankfurt)": "eu-central-1",
    "Canada (Central)": "ca-central-1",
    "South America (São Paulo)": "sa-east-1",
}


@tool
def parse_aws_alert_email(raw_email_body: str) -> str:
    """
    Parse a raw AWS alert email (SNS / CloudWatch Alarm notification)
    and extract structured alarm details.

    Args:
        raw_email_body: The full raw text body of the AWS alert email.

    Returns:
        A JSON string with extracted fields: alarm_name, new_state,
        region, account_id, timestamp, metric, reason.
    """
    result = {}

    # ── Try embedded JSON first (SNS direct emails) ────────────────
    json_match = re.search(r'\{[\s\S]*"AlarmName"[\s\S]*\}', raw_email_body)
    if json_match:
        try:
            payload = json.loads(json_match.group())
            result = {
                "alarm_name": payload.get("AlarmName", ""),
                "new_state": payload.get("NewStateValue", ""),
                "old_state": payload.get("OldStateValue", ""),
                "reason": payload.get("NewStateReason", ""),
                "region": payload.get("Region", ""),
                "account_id": payload.get("AWSAccountId", ""),
                "timestamp": payload.get("StateChangeTime", ""),
                "namespace": payload.get("Trigger", {}).get("Namespace", ""),
                "metric": payload.get("Trigger", {}).get("MetricName", ""),
            }
            logger.info("Parsed JSON alarm payload: %s", result.get("alarm_name"))
            return json.dumps(result, indent=2, default=str)
        except json.JSONDecodeError:
            pass

    # ── Region: extract from "in Asia Pacific (Mumbai)" pattern ────
    for region_name, region_code in REGION_MAP.items():
        if region_name in raw_email_body:
            result["region"] = region_code
            break
    if "region" not in result:
        # fallback: look for raw region code like ap-south-1
        m = re.search(r'\b([a-z]+-[a-z]+-\d+)\b', raw_email_body)
        if m:
            result["region"] = m.group(1)

    # ── Alarm name ─────────────────────────────────────────────────
    # Try: Alarm "name" pattern
    m = re.search(r'Alarm\s+"([^"]+)"', raw_email_body, re.IGNORECASE)
    if m:
        result["alarm_name"] = m.group(1).strip()
    else:
        # Try: - Name: value (stops at next - or newline)
        m = re.search(r'-\s*Name\s*:\s*(.+?)(?:\s+-\s|\n|$)', raw_email_body, re.IGNORECASE)
        if m:
            result["alarm_name"] = m.group(1).strip()

    # ── State ──────────────────────────────────────────────────────
    m = re.search(r'State Change\s*:\s*\w+\s*->\s*(ALARM|OK|INSUFFICIENT_DATA)', raw_email_body, re.IGNORECASE)
    if m:
        result["new_state"] = m.group(1).strip()

    # ── Timestamp: stop at " - " or newline ────────────────────────
    m = re.search(
        r'-\s*Timestamp\s*:\s*'
        r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'\s+\d{1,2}\s+\w+,\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+UTC'
        r'|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2}))',
        raw_email_body, re.IGNORECASE
    )
    if m:
        result["timestamp"] = m.group(1).strip()

    # ── Account ID ─────────────────────────────────────────────────
    m = re.search(r'-\s*AWS Account\s*:\s*(\d{12})', raw_email_body, re.IGNORECASE)
    if m:
        result["account_id"] = m.group(1).strip()

    # ── Metric ─────────────────────────────────────────────────────
    m = re.search(r'-\s*MetricName\s*:\s*(\w+)', raw_email_body, re.IGNORECASE)
    if m:
        result["metric"] = m.group(1).strip()

    # ── Reason: stop at " - Timestamp" ────────────────────────────
    m = re.search(
        r'-\s*Reason for State Change\s*:\s*(.+?)(?:\s+-\s*Timestamp|\n|$)',
        raw_email_body, re.IGNORECASE
    )
    if m:
        result["reason"] = m.group(1).strip()

    # ── Validate ───────────────────────────────────────────────────
    validation_errors = []
    if not result.get("alarm_name"):
        validation_errors.append("alarm_name not found")
    if not result.get("timestamp"):
        validation_errors.append("timestamp not found")
    if not result.get("region"):
        validation_errors.append("region not found")
    elif not _is_valid_aws_region(result["region"]):
        validation_errors.append(f"invalid region: {result['region']}")

    if validation_errors:
        result["validation_errors"] = validation_errors
        result["parse_confidence"] = "low"
        logger.warning("Parser validation errors: %s", validation_errors)
    else:
        result["parse_confidence"] = "high"

    if not result:
        result["raw_text"] = raw_email_body[:2000]
        result["parse_status"] = "Could not extract structured data."

    logger.info("Parsed alarm: %s | region=%s | timestamp=%s",
                result.get("alarm_name"), result.get("region"), result.get("timestamp"))
    return json.dumps(result, indent=2, default=str)
