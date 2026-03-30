---
name: email-parser
description: Parse incident or alert emails into structured fields such as service, environment, severity, timestamps, and error indicators. Use when the input is an alert email, message body, or raw incident text.
compatibility: Designed for AWS SNS/CloudWatch alarm email parsing
allowed-tools: email_parser
metadata:
  owner: platform-team
  version: "1.0"
---

# Email Parser

## Purpose
Parse raw alert or email content into normalized structured incident data, specifically for AWS CloudWatch alarm notifications.

## When to use
- When the workflow starts from an email or alert body
- When service, severity, environment, or timestamps need to be extracted from AWS notifications
- When downstream investigation tools need structured inputs
- As the first step in any AWS alarm investigation

## When not to use
- When the input is already normalized structured JSON
- When the request is about sending notifications rather than parsing content
- For non-AWS alert emails

## Required inputs
- `raw_email_body` — The full raw text body of the AWS alert email

## Workflow
1. Receive raw AWS alert email body (SNS or CloudWatch format)
2. Call `email_parser` to extract structured alarm details
3. Use extracted fields (alarm_name, timestamp, region, etc.) for downstream investigation
4. Proceed with service registry lookup and log fetching using extracted data

## Tool usage
- Call `email_parser` with the complete raw email body
- Extract key fields like alarm_name, timestamp, region for subsequent tools
- If confidence is low, return ambiguity notes instead of fabricating values

## Edge cases
- Forwarded or quoted email chains: Tool will attempt to find the original alarm data
- Multiple alarm notifications in one email: Tool will extract the primary alarm
- Malformed JSON in SNS payload: Tool will fall back to text parsing
- Missing critical fields: Tool will mark fields as uncertain rather than guess

## Output expectations
Returns structured alarm data with:
- `alarm_name` — Name of the CloudWatch alarm
- `new_state` — Current alarm state (ALARM, OK, INSUFFICIENT_DATA)
- `old_state` — Previous alarm state
- `reason` — Why the state changed
- `region` — AWS region
- `account_id` — AWS account ID
- `timestamp` — When the state changed
- `namespace` — CloudWatch metric namespace
- `metric` — Metric name
- `dimensions` — Metric dimensions
- `threshold` — Alarm threshold value
- `comparison` — Comparison operator used

## Examples

### Example 1: Parse SNS alarm notification
User request: Parse this AWS alarm email and identify the affected service
Action:
- Use `email_parser` with the raw email body
- Extract alarm_name, timestamp, and region for investigation
- Use extracted data for service registry lookup

### Example 2: Handle malformed email
User request: Parse this forwarded alarm email
Action:
- Use `email_parser` to attempt extraction
- Return structured data with confidence notes for uncertain fields
- Proceed with investigation using available data

## Integration with investigation workflow
This skill is typically the first step in the investigation workflow:
1. **email-parser** ← Parse the alert email
2. service-registry ← Look up service details
3. log-group-discovery ← Find the correct log group
4. cloudwatch-fetcher ← Fetch primary service logs
5. dependency-checker ← Check dependency logs
6. comprehensive-validator ← Validate all log fetches