"""
Tool: Log Group Discovery

Uses AWS Resource Explorer to dynamically search for CloudWatch log groups.
The agent uses this to find the right log group for an alarm instead of
relying on a static YAML mapping.
"""

import json
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_resource_explorer_client(region: str = None):
    """Create a boto3 Resource Explorer client."""
    import boto3
    from framework.config import Config

    config = Config()
    aws_config = config.aws_config

    session_kwargs = {}

    if aws_config.get("access_key_id") and aws_config.get("secret_access_key"):
        session_kwargs["aws_access_key_id"] = aws_config["access_key_id"]
        session_kwargs["aws_secret_access_key"] = aws_config["secret_access_key"]
        if aws_config.get("session_token"):
            session_kwargs["aws_session_token"] = aws_config["session_token"]

    if region:
        session_kwargs["region_name"] = region
    elif aws_config.get("region"):
        session_kwargs["region_name"] = aws_config["region"]

    session = boto3.Session(**session_kwargs)
    return session.client("resource-explorer-2")


@tool
def search_log_groups(
    query: str,
    region: str = "ap-south-1",
    max_results: int = 20,
) -> str:
    """
    Search for CloudWatch log groups in AWS using Resource Explorer.

    Use this tool BEFORE fetch_cloudwatch_logs when you don't know the exact log group name.
    It searches AWS Resource Explorer for log groups matching your query.

    Strategy for choosing the right query:
    - Extract the service name from the alarm name (e.g. 'qp-booking-service-common-error' → search 'booking')
    - You can also search by environment (e.g. 'prod', 'staging')
    - Use short, specific keywords for best results (e.g. 'booking', 'payment', 'notification')

    After getting results, YOU decide which log group is most relevant to the alarm
    and then call fetch_cloudwatch_logs with that log group name.

    Args:
        query: Search keyword to find relevant log groups (e.g. 'booking', 'payment-service', 'prod').
        region: AWS region. Default 'ap-south-1'.
        max_results: Maximum number of log groups to return. Default 20.

    Returns:
        A JSON string with matching log group names and their ARNs, or an error message.
    """
    try:
        client = _get_resource_explorer_client(region=region)

        # Build the Resource Explorer query string
        # Filter to only CloudWatch log groups and search by keyword
        search_query = f"resourcetype:logs:log-group {query}"

        logger.info(
            "Searching Resource Explorer for log groups: query='%s' region=%s",
            search_query, region,
        )

        response = client.search(
            QueryString=search_query,
            MaxResults=max_results,
        )

        log_groups = []
        for resource in response.get("Resources", []):
            arn = resource.get("Arn", "")
            # Extract log group name from ARN
            # ARN format: arn:aws:logs:region:account:log-group:/group/name:*
            log_group_name = ""
            if ":log-group:" in arn:
                log_group_name = arn.split(":log-group:")[-1]
                # Remove trailing :* if present
                if log_group_name.endswith(":*"):
                    log_group_name = log_group_name[:-2]

            log_groups.append({
                "log_group_name": log_group_name,
                "arn": arn,
                "region": resource.get("Region", region),
            })


        # Filter log groups to only those starting with '/copilot/'
        copilot_log_groups = [lg for lg in log_groups if lg["log_group_name"].startswith("/copilot/")]

        result = {
            "query": query,
            "search_query": search_query,
            "total_found": len(copilot_log_groups),
            "log_groups": copilot_log_groups,
        }

        if not copilot_log_groups:
            result["hint"] = (
                f"No /copilot/ log groups found for '{query}'. Try a broader search term "
                f"(e.g. just the service name like 'booking' instead of the full alarm name)."
            )

        logger.info(
            "Resource Explorer found %d /copilot/ log groups for query '%s'",
            len(copilot_log_groups), query,
        )
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        error_str = str(e)
        error_msg = {
            "error": error_str,
            "query": query,
        }

        # Provide helpful hints for common errors
        if "AccessDenied" in error_str:
            error_msg["hint"] = (
                "AWS Resource Explorer access denied. Make sure: "
                "1) Resource Explorer is enabled in your account, "
                "2) Your IAM role/user has 'resource-explorer-2:Search' permission."
            )
        elif "ResourceNotFoundException" in error_str or "No index" in error_str:
            error_msg["hint"] = (
                "Resource Explorer index not found. You need to create an index first: "
                "Go to AWS Console → Resource Explorer → Turn on Resource Explorer."
            )
        else:
            error_msg["hint"] = (
                "Failed to search log groups. Check that AWS Resource Explorer is enabled "
                "and credentials are valid."
            )

        logger.error("Resource Explorer search failed: %s", e)
        return json.dumps(error_msg, indent=2)
