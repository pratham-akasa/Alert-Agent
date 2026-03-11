---
name: service-registry
description: Look up service information including log groups, owner teams, dependencies, and operational context. Use when you need comprehensive service details for investigation or notification purposes.
compatibility: Designed for internal service registry lookups
allowed-tools: service_registry
metadata:
  owner: platform-team
  version: "1.0"
---

# Service Registry Lookup

## Purpose
Look up comprehensive service information including log groups, owner teams, dependencies, and operational context for incident investigation and notification.

## When to use
- **Always** call this tool after parsing an alert email to get full service context
- When you know an alarm name or service name and need complete service details
- When investigating cascading failures to check service dependencies
- Before sending notifications to get the correct team and channel information

## When not to use
- When you only need log group discovery (use log-group-discovery skill instead)
- For services not registered in the internal service registry

## Required inputs
- Either `alarm_name` (e.g., "qp-booking-service-common-error") OR `service_name` (e.g., "qp-booking-service")

## Workflow
1. Parse the alert email to extract `alarm_name`
2. Call `service_registry` with the alarm name or service name
3. Review returned service information including log groups, team, and dependencies
4. Use log groups for cloudwatch-fetcher if available
5. Use dependency information for dependency-checker
6. Use team and channel information for teams-notifier

## Tool usage
- Call `service_registry` with either alarm_name or service_name parameter
- Extract relevant information for downstream investigation steps
- Use dependency information to understand service relationships

## Edge cases
- Service not found in registry: Tool will return "not found" status
- Multiple services match: Tool will return the best match
- Incomplete service information: Tool will return available fields only
- Legacy or deprecated services: May have limited information

## Output expectations
Returns comprehensive service information:
- `log_groups` — CloudWatch log groups to fetch logs from
- `owner_team` — Team responsible for this service
- `depends_on` — Upstream dependencies (check these if root cause isn't obvious)
- `teams_channel` — MS Teams channel for notifications
- `runbook` — Link to the service's runbook (if available)
- `notes` — Operational notes (e.g., known batch job schedules)

## Examples

### Example 1: Complete service lookup
User request: Get service details for booking service alarm
Action:
- Use `service_registry` with alarm_name="qp-booking-service-common-error"
- Returns log groups, owner team, dependencies, and notification channels
- Use returned information for subsequent investigation steps

### Example 2: Dependency investigation
After finding issues in primary service:
- Use dependency information from service registry
- Call `service_registry` for each dependency to get their details
- Use dependency log groups for further investigation

## Integration with investigation workflow
This skill provides context for the entire investigation:
1. email-parser ← Parse the alert email
2. **service-registry** ← Get comprehensive service context
3. log-group-discovery ← Find log groups (if not provided by registry)
4. cloudwatch-fetcher ← Fetch logs using service information
5. dependency-checker ← Check dependencies identified by registry
6. teams-notifier ← Send notifications using team/channel information

## References
- See `references/service_dependencies_kb.md` for service dependency mappings