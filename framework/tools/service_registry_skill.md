# Skill: Service Registry Lookup

## When to Use
- **Always** call this tool after parsing an alert email to get full service context.
- Use it when you know an alarm name and need to find the matching log group, owner team, or dependencies.
- Use it when investigating cascading failures to check what services depend on the affected service.

## How to Use
Pass either an **alarm name** (e.g. `qp-booking-service-common-error`) or a **service name** (e.g. `qp-booking-service`).

The tool returns:
- `log_groups` — CloudWatch log groups to fetch logs from
- `owner_team` — Team responsible for this service
- `depends_on` — Upstream dependencies (check these if the root cause isn't obvious)
- `teams_channel` — MS Teams channel for notifications
- `runbook` — Link to the service's runbook (if available)
- `notes` — Operational notes (e.g. known batch job schedules)

## Workflow
1. Parse the alert email → extract `alarm_name`
2. Call `fetch_service_info(alarm_name)` → get log groups + context
3. Call `fetch_cloudwatch_logs(log_group)` with the log group from step 2
4. If logs suggest a dependency issue, call `fetch_service_info(dependency_name)` for upstream services
