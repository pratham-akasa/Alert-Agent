# Skill: Log Group Discovery

## When to Use
- Call this tool **BEFORE** `fetch_cloudwatch_logs` when you don't already know the exact log group name.
- Use the alarm name or service name from the parsed alert to search for relevant log groups.
- You do NOT need this tool if the service registry already gave you a log group name.

## How to Use
1. Extract the **service name** from the alarm (e.g. `qp-booking-service-common-error` → search for `booking`)
2. Call `search_log_groups(query="booking")`
3. Review the results and pick the most relevant log group (usually the production one)
4. Then call `fetch_cloudwatch_logs(log_group_name=<chosen_group>)`

## Query Tips
- Use **short, specific keywords**: `booking`, `payment`, `notification`
- Don't use the full alarm name — extract the service part
- If too many results, add the environment: `booking prod`
- If no results, try broader terms: `qp` instead of `qp-booking-service`

## Example Flow
```
1. parse_aws_alert_email → alarm_name: "qp-booking-service-common-error"
2. search_log_groups(query="booking") → finds ["/copilot/qp-prod-qp-booking-webservice", ...]
3. Agent picks "/copilot/qp-prod-qp-booking-webservice" (production log group)
4. fetch_cloudwatch_logs(log_group_name="/copilot/qp-prod-qp-booking-webservice")
```
