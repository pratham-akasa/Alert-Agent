---
name: teams-notifier
description: Send investigation summaries and alerts to Microsoft Teams channels. Use after completing investigation to notify responsible teams with findings and recommended actions.
compatibility: Designed for Microsoft Teams integration
allowed-tools: teams_notifier
metadata:
  owner: platform-team
  version: "1.0"
---

# MS Teams Notifier

## Purpose
Send investigation summaries and alerts to Microsoft Teams channels to notify responsible teams of incidents and recommended actions.

## When to use
- Call this tool **after** you have completed your investigation and have a final summary
- When you need to notify the responsible team about an incident
- As the final step in the investigation workflow after analysis is complete

## When not to use
- Before you have gathered sufficient context (parsed alert, fetched logs, checked dependencies)
- Before completing the investigation and having actionable findings
- Multiple times for the same alert (send once per investigation)

## Required inputs
- `summary` — Your full investigation summary (what happened, root cause, recommended action)
- `alarm_name` — The alarm that triggered (from the parsed email)
- `severity` — One of: Critical, High, Medium, Low, Info
- `owner_team` — The responsible team (from the service registry)
- `log_group` — The log group you investigated

## Workflow
1. Complete full investigation using other skills
2. Create comprehensive investigation summary
3. Determine appropriate severity level based on impact
4. Get owner team information from service registry
5. Call `teams_notifier` with complete information
6. Confirm notification was sent successfully

## Tool usage
- Call `teams_notifier` with all required parameters
- Ensure summary is comprehensive and actionable
- Use appropriate severity level based on impact assessment

## Severity guidelines
- **Critical** — Service is completely down, customer-facing impact
- **High** — Errors occurring actively, degraded service
- **Medium** — Elevated error rates but service is functional
- **Low** — Minor issue, no customer impact
- **Info** — Informational, e.g. auto-resolved alarm

## Edge cases
- Team channel not configured: Tool will report delivery failure
- Invalid severity level: Tool will reject the request
- Empty or insufficient summary: Tool will request more details
- Network/connectivity issues: Tool will report delivery status

## Output expectations
Returns notification status:
- Success confirmation with delivery details
- Failure notification with specific error information
- Channel and team information for verification

## Examples

### Example 1: High severity incident notification
After investigating a booking service error:
```
teams_notifier(
    summary="BookingController.createBooking() throwing NullPointerException. 5 errors in 2 minutes. Likely caused by null payment response from downstream payment service.",
    alarm_name="qp-booking-service-common-error",
    severity="High",
    owner_team="booking-platform",
    log_group="/copilot/qp-prod-qp-booking-webservice"
)
```

### Example 2: Auto-resolved alarm notification
For an alarm that resolved itself:
```
teams_notifier(
    summary="Temporary spike in response times resolved automatically. No errors found in logs. Likely caused by brief network latency.",
    alarm_name="qp-api-response-time-high",
    severity="Info",
    owner_team="platform-team",
    log_group="/copilot/qp-prod-api-gateway"
)
```

## Integration with investigation workflow
This skill is the final step in the investigation workflow:
1. email-parser ← Parse the alert email
2. service-registry ← Get service context and owner team
3. log-group-discovery ← Find log groups
4. cloudwatch-fetcher ← Fetch primary service logs
5. dependency-checker ← Check dependency logs
6. comprehensive-validator ← Validate log fetches
7. investigation-summary ← Format findings
8. **teams-notifier** ← Notify responsible team

## Best practices
- Always include specific error details in the summary
- Provide actionable recommendations when possible
- Use appropriate severity levels to avoid alert fatigue
- Include relevant log group and service information
- Send notifications promptly after investigation completion