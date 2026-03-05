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


@tool
def parse_aws_alert_email(raw_email_body: str) -> str:
    """
    Parse a raw AWS alert email (SNS / CloudWatch Alarm notification)
    and extract structured alarm details.

    Args:
        raw_email_body: The full raw text body of the AWS alert email.

    Returns:
        A JSON string with extracted fields: alarm_name, new_state,
        old_state, reason, region, account_id, timestamp, metric,
        namespace, and raw_payload (if JSON was embedded).
    """
    result = {}

    # ── Try to parse embedded JSON (common in SNS emails) ──────────
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
                "dimensions": payload.get("Trigger", {}).get("Dimensions", []),
                "threshold": payload.get("Trigger", {}).get("Threshold", ""),
                "comparison": payload.get("Trigger", {}).get("ComparisonOperator", ""),
                "raw_payload": payload,
            }
            logger.info("Parsed JSON alarm payload: %s", result.get("alarm_name"))
            return json.dumps(result, indent=2, default=str)
        except json.JSONDecodeError:
            logger.debug("JSON block found but could not parse, falling back to regex")

    # ── Fallback: regex-based parsing ──────────────────────────────
    patterns = {
        "new_state": r"(?:State\s*Change\s*:\s*\w+\s*->\s*(ALARM|OK|INSUFFICIENT_DATA)|(?:New\s+)?State\s*[:\s]\s*(ALARM|OK|INSUFFICIENT_DATA))",
        "reason": r"(?:Reason|State(?:\s+Change)?\s+Reason)[:\s]+(.+?)(?:\n|$)",
        "region": r"(?:Region)[:\s]+([\w-]+)",
        "account_id": r"(?:Account\s*(?:Id|ID)?)[:\s]+(\d{12})",
        "timestamp": r"(?:Time(?:stamp)?|State\s*Change\s*Time)[:\s]+(.+?)(?:\n|$)",
        "metric": r"(?:Metric(?:\s*Name)?)[:\s]+(.+?)(?:\n|$)",
        "namespace": r"(?:Namespace)[:\s]+(.+?)(?:\n|$)",
    }

    # Alarm name: try specific "- Name:" format first, then generic
    name_match = re.search(r"^-\s*Name\s*:\s*(.+?)\s*$", raw_email_body, re.IGNORECASE | re.MULTILINE)
    if not name_match:
        name_match = re.search(r"Alarm\s+Name\s*:\s*(.+?)\s*$", raw_email_body, re.IGNORECASE | re.MULTILINE)
    if not name_match:
        name_match = re.search(r'Alarm\s+"([^"]+)"', raw_email_body, re.IGNORECASE)
    if name_match:
        result["alarm_name"] = name_match.group(1).strip().strip('"')

    for field_name, pattern in patterns.items():
        match = re.search(pattern, raw_email_body, re.IGNORECASE | re.MULTILINE)
        if match:
            # For new_state, the value might be in group 1 or group 2
            if field_name == "new_state":
                result[field_name] = (match.group(1) or match.group(2) or "").strip()
            else:
                result[field_name] = match.group(1).strip()

    if not result:
        result["raw_text"] = raw_email_body[:2000]
        result["parse_status"] = "Could not extract structured data. Raw text attached."

    logger.info("Regex-parsed alarm fields: %s", list(result.keys()))
    return json.dumps(result, indent=2, default=str)
