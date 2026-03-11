---
name: cloudwatch-fetcher
description: Fetch recent log events from AWS CloudWatch Logs log groups for incident investigation. Use when you need to retrieve logs from a specific service around the time an alarm fired.
compatibility: Designed for AWS CloudWatch Logs investigation workflows
allowed-tools: cloudwatch_fetcher
metadata:
  owner: platform-team
  version: "1.0"
---

# CloudWatch Logs Fetcher

## Purpose
Queries AWS CloudWatch Logs to retrieve recent log events from a specified log group. Useful for investigating what happened around the time an alarm fired.

## When to use
- After parsing an alarm email, to fetch logs from the affected service
- When investigating errors, latency spikes, or exception patterns
- When you have a specific log group name and need to examine recent events

## When not to use
- When you don't know the log group name (use log-group-discovery skill first)
- When investigating multiple services simultaneously (use dependency-checker skill)

## Required inputs
- `log_group_name` — CloudWatch log group name (e.g. `/aws/lambda/my-function`)
- Optional: `filter_pattern` — CloudWatch filter pattern (e.g. `ERROR`, `{ $.level = "error" }`)
- Optional: `minutes_back` — How many minutes into the past to search (default: 30)
- Optional: `region` — AWS region (default: ap-south-1)
- Optional: `max_events` — Maximum number of log events to return (default: 50)

## Workflow
1. Ensure you have the correct log group name from service registry or log group discovery
2. Call `cloudwatch_fetcher` with the log group name and appropriate filters
3. Review the returned log events for errors, patterns, or anomalies
4. Use the timestamp information to correlate with alarm timing

## Tool usage
- Call `cloudwatch_fetcher` with required parameters
- **CRITICAL**: ONLY query log groups that are explicitly listed in the system instructions
- Do NOT guess or make up log group names

## Edge cases
- Log group doesn't exist: Tool will return an error
- No events in time window: Tool returns empty events array
- Large result sets: Use filter_pattern to narrow results
- Permission issues: Ensure proper AWS credentials and permissions

## Output expectations
Returns JSON with:
- `log_group` — The log group that was queried
- `filter_pattern` — The filter that was applied
- `time_range` — Start and end timestamps of the search window
- `event_count` — Number of log events found
- `events[]` — Array of log events with timestamp, log_stream, and message

## Examples

### Example 1: Basic error investigation
User request: Fetch recent ERROR logs from the booking service
Action:
- Use `cloudwatch_fetcher` with log_group_name="/copilot/qp-prod-qp-booking-webservice", filter_pattern="ERROR"
- Review error messages and timestamps

### Example 2: Specific time window investigation
User request: Check logs around alarm time with custom time window
Action:
- Use `cloudwatch_fetcher` with specific minutes_back parameter
- Correlate log timestamps with alarm timestamp