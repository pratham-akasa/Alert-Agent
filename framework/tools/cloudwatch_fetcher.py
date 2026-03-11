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
    from framework.core.config import Config

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
    alarm_timestamp: str = None,
) -> str:
    """
    Fetch recent log events from an AWS CloudWatch Logs log group.

    IMPORTANT: If you have the alarm timestamp from parse_aws_alert_email, you MUST pass it as alarm_timestamp parameter.
    This ensures logs are fetched from the correct time window when the alarm actually fired.

    You MUST choose appropriate values for minutes_back and max_events based on the alert:
    - If the alarm just fired (< 5 min ago), use minutes_back=10 and max_events=50
    - If the alarm fired a while ago, increase minutes_back to cover that window (e.g. 60 or 120)
    - For high-severity alarms or complex issues, increase max_events to 100-200 for more context
    - For simple threshold alarms, 50 events is usually enough
    - Use filter_pattern='ERROR' or '{ $.level = "error" }' to focus on errors when investigating error alarms

    Args:
        log_group_name: The CloudWatch log group path.
        filter_pattern: CloudWatch filter pattern to narrow results (e.g. 'ERROR', 'Exception', '{ $.level = "error" }').
        minutes_back: How many minutes into the past to search from the alarm timestamp. Choose based on when the alarm fired.
        region: AWS region. Default 'ap-south-1'.
        max_events: Maximum log events to return. Choose based on severity — more events = more context but slower.
        alarm_timestamp: The timestamp from the alarm email (from parse_aws_alert_email output). If provided, logs will be fetched around this time instead of current time.

    Returns:
        A JSON string with the fetched log events or an error message.
    """
    try:
        client = _get_cloudwatch_client(region=region)

        # Use alarm timestamp if provided, otherwise use current time
        if alarm_timestamp:
            try:
                # Try parsing various timestamp formats
                for fmt in [
                    "%A %d %B, %Y %H:%M:%S %Z",  # "Wednesday 04 March, 2026 04:08:18 UTC"
                    "%Y-%m-%dT%H:%M:%S%z",        # ISO format with timezone
                    "%Y-%m-%d %H:%M:%S",          # Simple format
                ]:
                    try:
                        end_time = datetime.strptime(alarm_timestamp, fmt)
                        if end_time.tzinfo is None:
                            end_time = end_time.replace(tzinfo=timezone.utc)
                        logger.info("Using alarm timestamp: %s", alarm_timestamp)
                        break
                    except ValueError:
                        continue
                else:
                    # If all formats fail, use current time
                    logger.warning("Could not parse alarm_timestamp '%s', using current time", alarm_timestamp)
                    end_time = datetime.now(timezone.utc)
            except Exception as e:
                logger.warning("Error parsing alarm_timestamp: %s, using current time", e)
                end_time = datetime.now(timezone.utc)
        else:
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
            "Fetching CloudWatch logs: group=%s pattern='%s' time_window=%s to %s",
            log_group_name, sanitized_pattern, start_time.isoformat(), end_time.isoformat(),
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
            "time_range": f"{start_time.isoformat()} → {end_time.isoformat()}",
            "alarm_timestamp_used": alarm_timestamp if alarm_timestamp else "current time",
            "event_count": len(events),
            "events": events,
            "validation": {
                "timestamp_source": "alarm" if alarm_timestamp else "current",
                "window_minutes": minutes_back,
                "aws_console_url": f"https://console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group_name.replace('/', '$252F')}/log-events$3FfilterPattern$3D{sanitized_pattern}$26start$3D{int(start_time.timestamp() * 1000)}$26end$3D{int(end_time.timestamp() * 1000)}",
                "expected_end_time": end_time.isoformat(),
                "expected_start_time": start_time.isoformat()
            }
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

