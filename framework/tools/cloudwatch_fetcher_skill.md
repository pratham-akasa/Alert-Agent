---
name: fetch_cloudwatch_logs
description: Fetch recent log events from an AWS CloudWatch Logs log group for investigation.
---

# CloudWatch Logs Fetcher

## Purpose
Queries AWS CloudWatch Logs to retrieve recent log events from a specified log group. Useful for investigating what happened around the time an alarm fired.

## Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `log_group_name` | string | Yes | — | CloudWatch log group name (e.g. `/aws/lambda/my-function`) |
| `filter_pattern` | string | No | `""` | CloudWatch filter pattern (e.g. `ERROR`, `{ $.level = "error" }`) |
| `minutes_back` | integer | No | `30` | How many minutes into the past to search |
| `region` | string | No | `ap-south-1` | AWS region |
| `max_events` | integer | No | `50` | Maximum number of log events to return |

## Output Fields
- `log_group` — The log group that was queried
- `filter_pattern` — The filter that was applied
- `time_range` — Start and end timestamps of the search window
- `event_count` — Number of log events found
- `events[]` — Array of log events, each with:
  - `timestamp` — When the log was written
  - `log_stream` — Which log stream it came from
  - `message` — The actual log message

## When to Use
- After parsing an alarm email, to fetch logs from the affected service
- When investigating errors, latency spikes, or exception patterns
- **CRITICAL**: ONLY query log groups that are explicitly listed in the "Log Group Mapping" found in your system instructions. Do NOT guess or make up log group names like `/aws/lambda/name`.


## Prerequisites
- The specified log group MUST exactly match a log group from the system instructions.

## Example
```
Input:  log_group_name="/copilot/qp-prod-qp-booking-webservice", filter_pattern="ERROR", minutes_back=15
Output: JSON with recent ERROR log events from the booking service
```
