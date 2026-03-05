"""
Tool: CloudWatch Logs Fetcher

Fetches recent log events from an AWS CloudWatch Logs log group
so the agent can inspect what happened around the time of an alarm.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_cloudwatch_client(region: str = None, profile: str = None):
    """Create a boto3 CloudWatch Logs client."""
    import boto3
    from framework.config import Config

    config = Config()
    aws_config = config.aws_config

    session_kwargs = {}
    
    # Try explicit credentials from config first
    if aws_config.get("access_key_id") and aws_config.get("secret_access_key"):
        session_kwargs["aws_access_key_id"] = aws_config["access_key_id"]
        session_kwargs["aws_secret_access_key"] = aws_config["secret_access_key"]
        if aws_config.get("session_token"):
            session_kwargs["aws_session_token"] = aws_config["session_token"]
    elif profile:
        session_kwargs["profile_name"] = profile

    if region:
        session_kwargs["region_name"] = region
    elif aws_config.get("region"):
        session_kwargs["region_name"] = aws_config["region"]

    session = boto3.Session(**session_kwargs)
    return session.client("logs")


@tool
def fetch_cloudwatch_logs(
    log_group_name: str,
    filter_pattern: str = "",
    minutes_back: int = 30,
    region: str = "ap-south-1",
    max_events: int = 50,
) -> str:
    """
    Fetch recent log events from an AWS CloudWatch Logs log group.

    You MUST choose appropriate values for minutes_back and max_events based on the alert:
    - If the alarm just fired (< 5 min ago), use minutes_back=10 and max_events=50
    - If the alarm fired a while ago, increase minutes_back to cover that window (e.g. 60 or 120)
    - For high-severity alarms or complex issues, increase max_events to 100-200 for more context
    - For simple threshold alarms, 50 events is usually enough
    - Use filter_pattern='ERROR' or '{ $.level = "error" }' to focus on errors when investigating error alarms

    Args:
        log_group_name: The CloudWatch log group path .
        filter_pattern: CloudWatch filter pattern to narrow results (e.g. 'ERROR', 'Exception', '{ $.level = "error" }').
        minutes_back: How many minutes into the past to search. Choose based on when the alarm fired.
        region: AWS region. Default 'ap-south-1'.
        max_events: Maximum log events to return. Choose based on severity — more events = more context but slower.

    Returns:
        A JSON string with the fetched log events or an error message.
    """
    try:
        client = _get_cloudwatch_client(region=region)

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes_back)

        # Sanitize filter_pattern: remove invalid wildcard characters
        sanitized_pattern = filter_pattern.replace('*', '').replace('?', '').strip() if filter_pattern else ''

        kwargs = {
            "logGroupName": log_group_name,
            "startTime": int(start_time.timestamp() * 1000),
            "endTime": int(end_time.timestamp() * 1000),
            "limit": max_events,
            "interleaved": True,
        }
        if sanitized_pattern:
            kwargs["filterPattern"] = sanitized_pattern

        logger.info(
            "Fetching CloudWatch logs: group=%s pattern='%s' minutes_back=%d",
            log_group_name, sanitized_pattern, minutes_back,
        )

        response = client.filter_log_events(**kwargs)

        events = []
        for evt in response.get("events", []):
            events.append({
                "timestamp": datetime.fromtimestamp(
                    evt["timestamp"] / 1000, tz=timezone.utc
                ).isoformat(),
                "log_stream": evt.get("logStreamName", ""),
                "message": evt.get("message", "").strip(),
            })

        result = {
            "log_group": log_group_name,
            "filter_pattern": sanitized_pattern,
            "time_range": f"{start_time.isoformat()}  {end_time.isoformat()}",
            "event_count": len(events),
            "events": events,
        }

        logger.info("Fetched %d log events from %s", len(events), log_group_name)
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        error_msg = {
            "error": str(e),
            "log_group": log_group_name,
            "hint": "Check that the log group exists and AWS credentials are configured.",
        }
        logger.error("CloudWatch fetch failed: %s", e)
        return json.dumps(error_msg, indent=2)
