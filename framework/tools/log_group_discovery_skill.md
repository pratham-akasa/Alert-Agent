# Skill: Log Group Discovery

## When to Use
- Call **`discover_log_group(alarm_name)`** BEFORE `fetch_cloudwatch_logs` when investigating an alarm.
- This is the **primary tool** to find the right log group. It automatically extracts keywords from the alarm name, tries multiple prioritized queries, and returns the best matching `/copilot/` log group (preferring production environments).
- You do NOT need this tool if the service registry already gave you a log group name.

## Primary Workflow
1. Parse the alert to get the `alarm_name` (e.g., `qp-booking-service-common-error`)
2. Call `discover_log_group(alarm_name="qp-booking-service-common-error")`
3. If it returns a log group (e.g., `/copilot/qp-prod-qp-booking-webservice`), call `fetch_cloudwatch_logs` with it.
4. If it fails to find anything, see "Fallback Workflow" below.

## Fallback Workflow (`search_log_groups`)
If `discover_log_group` returns `not_found`, or if you need to manually explore log groups:
- Use the `search_log_groups(query)` tool.
- Provide a custom, broad query (e.g. `query="booking"` instead of the full service name).
- Review the results and manually select the best one.

## Example Flow
```
1. parse_aws_alert_email → alarm_name: "qp-booking-service-common-error"
2. discover_log_group(alarm_name="qp-booking-service-common-error") 
   → Automatically tries "booking-service", "booking", etc.
   → Returns "/copilot/qp-prod-qp-booking-webservice"
3. fetch_cloudwatch_logs(log_group_name="/copilot/qp-prod-qp-booking-webservice")
```
