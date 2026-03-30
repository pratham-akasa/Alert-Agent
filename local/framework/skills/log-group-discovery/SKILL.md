---
name: log-group-discovery
description: Discover the correct CloudWatch log group for a service based on alarm names or service identifiers. Use when you need to find log groups before fetching logs for investigation.
compatibility: Designed for AWS CloudWatch log group discovery
allowed-tools: log_group_discovery
metadata:
  owner: platform-team
  version: "1.0"
---

# Log Group Discovery

## Purpose
Discover the correct CloudWatch log group for a service based on alarm names or service identifiers, with automatic keyword extraction and prioritized querying.

## When to use
- Call **BEFORE** cloudwatch-fetcher when investigating an alarm
- When you have an alarm name but need to find the corresponding log group
- When service registry doesn't provide a log group name
- As the primary tool to find the right log group automatically

## When not to use
- When you already have the log group name from service registry
- When investigating multiple services simultaneously (use dependency-checker instead)

## Required inputs
- `alarm_name` — The alarm name from parsed email (e.g., "qp-booking-service-common-error")
- Optional: Custom search query for manual exploration

## Workflow
1. Parse the alert to get the `alarm_name`
2. Call `log_group_discovery` with the alarm name
3. Tool automatically extracts keywords and tries multiple prioritized queries
4. If successful, use returned log group with cloudwatch-fetcher
5. If unsuccessful, use fallback workflow with manual search

## Tool usage
- Primary: Call `discover_log_group(alarm_name="alarm-name-here")`
- Fallback: Call `search_log_groups(query="custom-search-term")` for manual exploration
- Tool automatically tries multiple search strategies and returns best match

## Primary workflow
1. Parse the alert → get `alarm_name` (e.g., `qp-booking-service-common-error`)
2. Call `discover_log_group(alarm_name="qp-booking-service-common-error")`
3. Tool automatically tries "booking-service", "booking", etc.
4. Returns best matching `/copilot/` log group (preferring production environments)
5. Use returned log group with cloudwatch-fetcher

## Fallback workflow
If `discover_log_group` returns `not_found`:
1. Use `search_log_groups(query="broader-search-term")`
2. Provide a custom, broad query (e.g. `query="booking"` instead of full service name)
3. Review the results and manually select the best one
4. Use selected log group with cloudwatch-fetcher

## Edge cases
- No matching log groups found: Tool returns `not_found`, use fallback workflow
- Multiple potential matches: Tool returns the best match based on priority rules
- Ambiguous service names: Tool tries multiple keyword variations
- Non-standard naming: May require manual search with broader terms

## Output expectations
Returns either:
- **Success**: Best matching log group path (e.g., `/copilot/qp-prod-qp-booking-webservice`)
- **Not found**: `not_found` status, requiring fallback workflow
- **Multiple options**: List of potential matches for manual selection

## Examples

### Example 1: Successful automatic discovery
User request: Find log group for booking service alarm
Action:
- Use `discover_log_group(alarm_name="qp-booking-service-common-error")`
- Tool automatically extracts "booking-service", "booking" keywords
- Returns `/copilot/qp-prod-qp-booking-webservice`

### Example 2: Fallback manual search
When automatic discovery fails:
- Use `search_log_groups(query="booking")`
- Review returned options
- Select most appropriate log group
- Proceed with cloudwatch-fetcher

## Integration with investigation workflow
This skill fits into the investigation workflow as:
1. email-parser ← Parse the alert email
2. service-registry ← Look up service details (may provide log group)
3. **log-group-discovery** ← Find log group if not provided by registry
4. cloudwatch-fetcher ← Fetch logs using discovered log group
5. dependency-checker ← Check dependency logs
6. comprehensive-validator ← Validate all log fetches