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


def _is_valid_aws_timestamp(timestamp_str: str) -> bool:
    """Check if timestamp string is in a valid AWS format."""
    import re
    
    # AWS CloudWatch format: "Tuesday 10 March, 2026 04:08:18 UTC"
    aws_pattern = r'^[A-Za-z]+\s+\d{1,2}\s+[A-Za-z]+,\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+UTC$'
    
    # ISO format: "2026-03-10T04:08:18Z" or "2026-03-10T04:08:18+00:00"
    iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$'
    
    # Simple UTC format: "2026-03-10 04:08:18 UTC"
    simple_pattern = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+UTC$'
    
    return (re.match(aws_pattern, timestamp_str) or 
            re.match(iso_pattern, timestamp_str) or 
            re.match(simple_pattern, timestamp_str))


def _is_valid_aws_region(region_str: str) -> bool:
    """Check if region string is a valid AWS region code."""
    # Common AWS regions
    valid_regions = {
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
        'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-central-1',
        'ap-south-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
        'ap-northeast-2', 'ca-central-1', 'sa-east-1'
    }
    return region_str in valid_regions


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
        "reason": r"(?:Reason\s+for\s+State\s+Change|State(?:\s+Change)?\s+Reason)[:\s]+(.+?)(?:\n|$)",
        "region": r"(?:in\s+the\s+|region\s+)([a-z]+-[a-z]+-\d+)(?:\s+region|\s|$)",
        "account_id": r"(?:Account\s*(?:Id|ID)?)[:\s]+(\d{12})",
        "timestamp": r"(?:Timestamp)[:\s]+(.+?)(?:\n|$)",
        "metric": r"(?:MetricName)[:\s]+(.+?)(?:\n|$)",
        "namespace": r"(?:Namespace)[:\s]+(.+?)(?:\n|$)",
    }

    # Extract region from subject line if available (more reliable)
    subject_region_match = re.search(r'in\s+([^)]+)\)', raw_email_body)
    if subject_region_match:
        region_text = subject_region_match.group(1).strip()
        # Map common region names to AWS region codes
        region_mapping = {
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
        # Try exact match first
        if region_text in region_mapping:
            result["region"] = region_mapping[region_text]
        else:
            # Fallback: try to extract region code if it's already in the text
            region_code_match = re.search(r'([a-z]+-[a-z]+-\d+)', region_text.lower())
            if region_code_match:
                result["region"] = region_code_match.group(1)
            else:
                # Last resort: sanitize the text
                result["region"] = region_text.lower().replace(" ", "-").replace("(", "").replace(")", "")

    # Alarm name: try specific "- Name:" format first, then generic
    name_match = re.search(r"^-\s*Name\s*:\s*(.+?)\s*$", raw_email_body, re.IGNORECASE | re.MULTILINE)
    if not name_match:
        name_match = re.search(r"Alarm\s+Name\s*:\s*(.+?)\s*$", raw_email_body, re.IGNORECASE | re.MULTILINE)
    if not name_match:
        name_match = re.search(r'Alarm\s+"([^"]+)"', raw_email_body, re.IGNORECASE)
    if name_match:
        result["alarm_name"] = name_match.group(1).strip().strip('"')

    for field_name, pattern in patterns.items():
        # Skip region if we already extracted it from subject
        if field_name == "region" and "region" in result:
            continue
            
        match = re.search(pattern, raw_email_body, re.IGNORECASE | re.MULTILINE)
        if match:
            # For new_state, the value might be in group 1 or group 2
            if field_name == "new_state":
                result[field_name] = (match.group(1) or match.group(2) or "").strip()
            else:
                result[field_name] = match.group(1).strip()

    # Validate extracted values before returning
    validation_errors = []
    
    if not result.get("alarm_name"):
        validation_errors.append("alarm_name not found")
    
    if not result.get("timestamp"):
        validation_errors.append("timestamp not found")
    elif not _is_valid_aws_timestamp(result["timestamp"]):
        validation_errors.append(f"invalid timestamp format: {result['timestamp']}")
    
    if not result.get("region"):
        validation_errors.append("region not found")
    elif not _is_valid_aws_region(result["region"]):
        validation_errors.append(f"invalid region: {result['region']}")
    
    if validation_errors:
        result["validation_errors"] = validation_errors
        result["parse_confidence"] = "low"
        logger.warning("Parser validation errors: %s", validation_errors)

    if not result:
        result["raw_text"] = raw_email_body[:2000]
        result["parse_status"] = "Could not extract structured data. Raw text attached."

    logger.info("Regex-parsed alarm fields: %s", list(result.keys()))
    return json.dumps(result, indent=2, default=str)
