"""
Tool: Dependency Checker

Automatically checks service dependencies and fetches their logs.
"""

import json
import logging
import os
import re
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _normalize_service_name_for_search(service_name: str) -> list[str]:
    """
    Generate search queries for a dependency service name.
    
    Examples:
        'NavOds-Webservice' -> ['navods', 'nav-ods', 'nav-ods-webservice', 'navods-webservice']
        'data-transfer-service' -> ['data-transfer', 'data-transfer-service']
    
    Returns:
        List of search queries in priority order
    """
    name = service_name.lower().strip()
    
    # Remove common suffixes
    suffixes = ['-webservice', '-service', '-api']
    base = name
    for suffix in suffixes:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    
    queries = []
    
    # Priority 1: Base name without suffix (e.g., 'navods', 'data-transfer')
    if base:
        queries.append(base)
    
    # Priority 2: Base with hyphens normalized (e.g., 'nav-ods' from 'navods')
    # Insert hyphens between camelCase or known patterns
    if base and '-' not in base and len(base) > 4:
        # Try to split camelCase-like patterns
        import re
        # Insert hyphen before capital letters (for patterns like NavOds -> nav-ods)
        hyphenated = re.sub(r'([a-z])([A-Z])', r'\1-\2', base).lower()
        if hyphenated != base:
            queries.append(hyphenated)
    
    # Priority 3: Full original name (e.g., 'navods-webservice')
    if name != base:
        queries.append(name)
    
    # De-duplicate
    seen = set()
    unique = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            unique.append(q)
    
    return unique[:3]  # Max 3 queries


def _search_for_dependency_log_group(re_client, dependency_name: str, region: str, max_results: int = 20):
    """
    Search for a dependency's log group with smart query generation.
    
    Returns:
        Best matching log group dict or None
    """
    from framework.tools.log_group_discovery import _search_resource_explorer, _rank_log_groups
    
    queries = _normalize_service_name_for_search(dependency_name)
    logger.info("Searching for dependency '%s' with queries: %s", dependency_name, queries)
    
    for query in queries:
        matches = _search_resource_explorer(re_client, query, max_results)
        
        if matches:
            # Filter matches to prefer ones that contain the query term
            # This prevents 'navods' from matching 'common-webservice'
            query_parts = query.replace('-', '').lower()
            
            filtered = []
            for match in matches:
                log_group_lower = match["log_group_name"].lower()
                # Check if the log group name contains the query term
                if query_parts in log_group_lower.replace('-', '').replace('/', ''):
                    filtered.append(match)
            
            if filtered:
                ranked = _rank_log_groups(filtered)
                logger.info("Found log group '%s' for dependency '%s' using query '%s'", 
                           ranked[0]["log_group_name"], dependency_name, query)
                return ranked[0]
            else:
                logger.info("Query '%s' found matches but none contained the search term", query)
    
    logger.warning("No matching log group found for dependency '%s'", dependency_name)
    return None


def _parse_dependencies_from_kb(service_name: str) -> list[str]:
    """Parse service dependencies from the knowledge base file."""
    # In Lambda, the file is at /app/framework/skills/...
    file_path = os.path.join(
        "/app",  # Lambda working directory
        "framework", "skills", "service-registry", "references", "service_dependencies_kb.md"
    )
    
    if not os.path.exists(file_path):
        logger.warning("Dependencies KB file not found at %s", file_path)
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Look for the service section (case-insensitive)
        # Pattern: ## service-name followed by dependencies as list items
        pattern = rf"##\s+{re.escape(service_name)}.*?\n(.*?)(?=\n##|\n---|\Z)"
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        
        if not match:
            logger.info("No dependencies section found for service '%s'", service_name)
            return []
        
        section = match.group(1)
        
        # Extract list items (lines starting with -)
        dependencies = []
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                dep = line.lstrip('-').strip()
                if dep:
                    dependencies.append(dep)
        
        logger.info("Found %d dependencies for '%s': %s", len(dependencies), service_name, dependencies)
        return dependencies
        
    except Exception as e:
        logger.error("Error parsing dependencies KB: %s", e)
        return []


def _extract_service_name_from_alarm(alarm_name: str) -> str:
    """
    Extract service name from alarm name.
    E.g., 'qp-booking-service-common-error' -> 'qp-booking-webservice'
    """
    # Remove common alarm suffixes
    suffixes = ['-common-error', '-critical-error', '-error', '-alarm', '-high', '-low']
    name = alarm_name.lower()
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    
    # Try to match with common service naming patterns
    # booking-service -> booking-webservice
    if 'booking' in name:
        return 'qp-booking-webservice'
    
    return name


@tool
def check_service_dependencies(alarm_name: str, region: str = "ap-south-1", alarm_timestamp: str = None) -> str:
    """
    Automatically check service dependencies and fetch their CloudWatch logs.

    This tool:
    1. Extracts the service name from the alarm
    2. Looks up dependencies in the knowledge base
    3. For each dependency: discovers log group and fetches recent ERROR logs
    4. Returns a comprehensive report of all dependency logs

    Use this tool AFTER fetching logs from the primary service to check if
    dependencies are the root cause of the alarm.

    Args:
        alarm_name: The alarm name (e.g., 'qp-booking-service-common-error')
        region: AWS region. Default 'ap-south-1'
        alarm_timestamp: The timestamp from the alarm email (from parse_aws_alert_email output).
                        If provided, logs will be fetched around this time instead of current time.

    Returns:
        JSON string with dependency analysis and all fetched logs
    """
    
    # CRITICAL VALIDATION: Warn if alarm_timestamp is missing
    if not alarm_timestamp:
        logger.warning("⚠️ CRITICAL: check_service_dependencies called WITHOUT alarm_timestamp!")
        logger.warning("⚠️ Dependencies will be checked at CURRENT time instead of alarm time!")
        logger.warning("⚠️ You MUST pass the timestamp from parse_aws_alert_email!")
    
    from framework.tools.log_group_discovery import _get_resource_explorer_client, _search_resource_explorer, _rank_log_groups
    from framework.tools.cloudwatch_fetcher import _get_cloudwatch_client
    from datetime import datetime, timedelta, timezone

    logger.info("check_service_dependencies: alarm='%s', timestamp='%s'", alarm_name, alarm_timestamp)

    # Extract service name
    service_name = _extract_service_name_from_alarm(alarm_name)

    # Get dependencies from KB
    dependencies = _parse_dependencies_from_kb(service_name)

    if not dependencies:
        return json.dumps({
            "status": "no_dependencies",
            "alarm_name": alarm_name,
            "service_name": service_name,
            "message": f"No dependencies found for service '{service_name}' in the knowledge base.",
            "hint": "The primary service may be the root cause, or dependencies are not documented yet."
        }, indent=2)

    # Process each dependency
    results = {
        "status": "completed",
        "alarm_name": alarm_name,
        "service_name": service_name,
        "dependencies_checked": len(dependencies),
        "dependency_results": []
    }

    try:
        re_client = _get_resource_explorer_client(region=region)
        cw_client = _get_cloudwatch_client(region=region)

        # Calculate time window based on alarm timestamp or current time
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
                        logger.info("Using alarm timestamp for dependencies: %s", alarm_timestamp)
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

        start_time = end_time - timedelta(minutes=10)

        for dep in dependencies:
            dep_result = {
                "dependency_name": dep,
                "log_group": None,
                "logs_fetched": False,
                "error_count": 0,
                "errors": []
            }

            try:
                # Discover log group for dependency using smart search
                logger.info("Discovering log group for dependency: %s", dep)
                best_match = _search_for_dependency_log_group(re_client, dep, region, max_results=20)

                if best_match:
                    log_group = best_match["log_group_name"]
                    dep_result["log_group"] = log_group

                    # Fetch logs using the same timestamp as the alarm
                    logger.info("Fetching logs from dependency log group: %s", log_group)

                    response = cw_client.filter_log_events(
                        logGroupName=log_group,
                        startTime=int(start_time.timestamp() * 1000),
                        endTime=int(end_time.timestamp() * 1000),
                        filterPattern="ERROR",
                        limit=50,
                        interleaved=True,
                    )

                    events = []
                    for evt in response.get("events", []):
                        events.append({
                            "timestamp": datetime.fromtimestamp(
                                evt["timestamp"] / 1000, tz=timezone.utc
                            ).isoformat(),
                            "message": evt.get("message", "").strip()[:500]  # Truncate long messages
                        })

                    dep_result["logs_fetched"] = True
                    dep_result["error_count"] = len(events)
                    dep_result["errors"] = events
                    dep_result["time_range"] = f"{start_time.isoformat()} → {end_time.isoformat()}"
                    dep_result["alarm_timestamp_used"] = alarm_timestamp if alarm_timestamp else "current time"

                    logger.info("Fetched %d ERROR logs from %s", len(events), dep)
                else:
                    dep_result["message"] = f"No log group found for dependency '{dep}'"
                    logger.warning("No log group found for dependency: %s", dep)

            except Exception as e:
                dep_result["error"] = str(e)
                logger.error("Error processing dependency %s: %s", dep, e)

            results["dependency_results"].append(dep_result)

        # Add summary
        total_errors = sum(r["error_count"] for r in results["dependency_results"])
        results["summary"] = {
            "total_dependency_errors": total_errors,
            "dependencies_with_errors": sum(1 for r in results["dependency_results"] if r["error_count"] > 0),
            "analysis": (
                f"Found {total_errors} ERROR logs across {len(dependencies)} dependencies. "
                f"{'Root cause likely in dependencies.' if total_errors > 0 else 'Dependencies look healthy.'}"
            )
        }

        return json.dumps(results, indent=2, default=str)

    except Exception as e:
        logger.error("check_service_dependencies failed: %s", e)
        return json.dumps({
            "status": "error",
            "alarm_name": alarm_name,
            "error": str(e),
            "dependencies_attempted": dependencies
        }, indent=2)
