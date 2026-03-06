"""
Tool: Log Group Discovery

Uses AWS Resource Explorer to dynamically search for CloudWatch log groups.
The agent uses this to find the right log group for an alarm instead of
relying on a static YAML mapping.
"""

import json
import logging
import re
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── Known suffixes to strip when extracting service name from alarm ────
_ALARM_SUFFIXES = [
    "-common-error",
    "-critical-error",
    "-high-error",
    "-low-error",
    "-error-alarm",
    "-error",
    "-alarm",
    "-critical",
    "-warning",
    "-high",
    "-low",
    "-threshold",
    "-anomaly",
]


def _extract_search_queries(alarm_name: str) -> list[str]:
    """
    Generate up to 5 prioritised search queries from an alarm name.

    Priority order (most specific → broadest):
      1. Core service name  (e.g. "booking-service")
      2. Full service name with prefix  (e.g. "qp-booking-service")
      3. Primary keyword  (e.g. "booking")
      4. Prefix + primary keyword  (e.g. "qp-booking")
      5. Extended service name  (e.g. "booking-service-common")

    Returns de-duplicated list in priority order, max 5 entries.
    """
    name = alarm_name.strip().lower()

    # ── Strip known alarm-type suffixes ────────────────────────────
    base = name
    for suffix in sorted(_ALARM_SUFFIXES, key=len, reverse=True):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break  # only strip the first (longest) matching suffix

    parts = base.split("-")

    # ── Detect project prefix (first token if ≤ 3 chars, e.g. "qp") ──
    prefix = ""
    service_parts = parts
    if len(parts) > 1 and len(parts[0]) <= 3:
        prefix = parts[0]
        service_parts = parts[1:]

    queries: list[str] = []

    # P1: core service name without prefix  ("booking-service")
    if len(service_parts) >= 2:
        queries.append("-".join(service_parts))
    elif service_parts:
        queries.append(service_parts[0])

    # P2: full service name with prefix  ("qp-booking-service")
    if prefix:
        queries.append("-".join([prefix] + service_parts))

    # P3: primary keyword  ("booking")
    if service_parts:
        queries.append(service_parts[0])

    # P4: prefix + primary keyword  ("qp-booking")
    if prefix and service_parts:
        queries.append(f"{prefix}-{service_parts[0]}")

    # P5: extended name — original base (with suffix stripped) if different
    if base not in queries:
        queries.append(base)

    # De-duplicate while preserving order, cap at 5
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            unique.append(q)
        if len(unique) == 5:
            break

    return unique


def _rank_log_groups(log_groups: list[dict]) -> list[dict]:
    """
    Sort log groups so production ones come first.

    Ranking: groups containing 'prod' > others > groups containing 'staging'/'dev'/'test'.
    """
    def _score(lg: dict) -> int:
        name = lg.get("log_group_name", "").lower()
        if "prod" in name:
            return 0
        if any(env in name for env in ("staging", "stg", "dev", "test", "sandbox")):
            return 2
        return 1

    return sorted(log_groups, key=_score)


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


def _search_resource_explorer(client, query: str, max_results: int = 20):
    """
    Run a single Resource Explorer search and return /copilot/ log groups.

    Returns a list of dicts with log_group_name, arn, region.
    """
    search_query = f"resourcetype:logs:log-group {query}"

    logger.info(
        "Searching Resource Explorer: query='%s'", search_query,
    )

    response = client.search(
        QueryString=search_query,
        MaxResults=max_results,
    )

    log_groups = []
    for resource in response.get("Resources", []):
        arn = resource.get("Arn", "")
        log_group_name = ""
        if ":log-group:" in arn:
            log_group_name = arn.split(":log-group:")[-1]
            if log_group_name.endswith(":*"):
                log_group_name = log_group_name[:-2]

        log_groups.append({
            "log_group_name": log_group_name,
            "arn": arn,
            "region": resource.get("Region", ""),
        })

    # Keep only /copilot/ log groups
    return [lg for lg in log_groups if lg["log_group_name"].startswith("/copilot/")]


# ── Tools ──────────────────────────────────────────────────────────────


@tool
def search_log_groups(
    query: str,
    region: str = "ap-south-1",
    max_results: int = 20,
) -> str:
    """
    Search for CloudWatch log groups in AWS using Resource Explorer.

    Use this tool for manual / ad-hoc searches when you already know the
    keyword to search for. For alarm investigation, prefer discover_log_group
    which automates multi-query prioritised search.

    Args:
        query: Search keyword to find relevant log groups (e.g. 'booking', 'payment-service', 'prod').
        region: AWS region. Default 'ap-south-1'.
        max_results: Maximum number of log groups to return. Default 20.

    Returns:
        A JSON string with matching /copilot/ log group names and their ARNs, or an error message.
    """
    try:
        client = _get_resource_explorer_client(region=region)
        copilot_log_groups = _search_resource_explorer(client, query, max_results)

        result = {
            "query": query,
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


@tool
def discover_log_group(
    alarm_name: str,
    region: str = "ap-south-1",
    max_results: int = 20,
) -> str:
    """
    Automatically discover the best CloudWatch log group for a given alarm.

    This is the PRIMARY tool for alarm investigation. It:
    1. Extracts the service name from the alarm name.
    2. Generates up to 5 prioritised search queries (most specific first).
    3. Tries each query against AWS Resource Explorer in order.
    4. Returns only /copilot/ log groups, ranked with production first.
    5. Stops as soon as matching log groups are found.

    Use this BEFORE fetch_cloudwatch_logs when investigating an alarm.

    Args:
        alarm_name: The alarm name from the parsed alert (e.g. 'qp-booking-service-common-error').
        region: AWS region. Default 'ap-south-1'.
        max_results: Maximum results per query. Default 20.

    Returns:
        A JSON string with the best matching log group, all candidates,
        the queries tried, and which query succeeded.
    """
    queries = _extract_search_queries(alarm_name)
    logger.info(
        "discover_log_group: alarm='%s' → queries=%s", alarm_name, queries,
    )

    tried: list[dict] = []

    try:
        client = _get_resource_explorer_client(region=region)

        for priority, query in enumerate(queries, start=1):
            matches = _search_resource_explorer(client, query, max_results)
            tried.append({
                "priority": priority,
                "query": query,
                "matches_found": len(matches),
            })

            if matches:
                ranked = _rank_log_groups(matches)
                best = ranked[0]

                result = {
                    "status": "found",
                    "alarm_name": alarm_name,
                    "best_log_group": best["log_group_name"],
                    "best_log_group_arn": best["arn"],
                    "matched_query": query,
                    "matched_priority": priority,
                    "all_candidates": ranked,
                    "queries_tried": tried,
                }
                logger.info(
                    "discover_log_group: found '%s' via query '%s' (priority %d)",
                    best["log_group_name"], query, priority,
                )
                return json.dumps(result, indent=2, default=str)

            logger.info(
                "discover_log_group: no /copilot/ matches for query '%s' (priority %d), trying next…",
                query, priority,
            )

        # All queries exhausted
        result = {
            "status": "not_found",
            "alarm_name": alarm_name,
            "queries_tried": tried,
            "hint": (
                f"No /copilot/ log groups found for alarm '{alarm_name}' after trying "
                f"{len(queries)} queries: {queries}. "
                "Try search_log_groups with a custom keyword, or check if the service "
                "uses a non-standard log group naming convention."
            ),
        }
        logger.warning(
            "discover_log_group: no log group found for '%s' after %d queries",
            alarm_name, len(queries),
        )
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        error_str = str(e)
        error_msg = {
            "status": "error",
            "alarm_name": alarm_name,
            "error": error_str,
            "queries_tried": tried,
        }

        if "AccessDenied" in error_str:
            error_msg["hint"] = (
                "AWS Resource Explorer access denied. Check IAM permissions "
                "for 'resource-explorer-2:Search'."
            )
        elif "ResourceNotFoundException" in error_str or "No index" in error_str:
            error_msg["hint"] = (
                "Resource Explorer index not found. Enable it in the AWS Console."
            )
        else:
            error_msg["hint"] = (
                "Failed to search log groups. Verify AWS Resource Explorer is enabled "
                "and credentials are valid."
            )

        logger.error("discover_log_group failed: %s", e)
        return json.dumps(error_msg, indent=2)
