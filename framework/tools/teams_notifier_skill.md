# Skill: MS Teams Notifier

## When to Use
- Call this tool **after** you have completed your investigation and have a final summary.
- Do NOT call it before you have gathered sufficient context (parsed alert, fetched logs, checked service registry).
- Call it once per alert investigation — do not send multiple messages for the same alert.

## How to Use
Pass the following:
- `summary` — Your full investigation summary (what happened, root cause, recommended action)
- `alarm_name` — The alarm that triggered (from the parsed email)
- `severity` — One of: Critical, High, Medium, Low, Info
- `owner_team` — The responsible team (from the service registry)
- `log_group` — The log group you investigated

## Severity Guidelines
- **Critical** — Service is completely down, customer-facing impact
- **High** — Errors occurring actively, degraded service
- **Medium** — Elevated error rates but service is functional
- **Low** — Minor issue, no customer impact
- **Info** — Informational, e.g. auto-resolved alarm

## Example
After investigating a booking service error:
```
notify_teams(
    summary="BookingController.createBooking() throwing NullPointerException. 5 errors in 2 minutes. Likely caused by null payment response from downstream payment service.",
    alarm_name="qp-booking-service-common-error",
    severity="High",
    owner_team="booking-platform",
    log_group="/copilot/qp-prod-qp-booking-webservice"
)
```
