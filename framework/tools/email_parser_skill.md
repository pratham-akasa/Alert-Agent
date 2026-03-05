---
name: parse_aws_alert_email
description: Parse raw AWS alert emails (SNS / CloudWatch Alarm notifications) and extract structured alarm details.
---

# AWS Alert Email Parser

## Purpose
Parses raw AWS alert email bodies—both JSON-embedded SNS payloads and plain-text CloudWatch alarm notifications—and extracts structured information.

## Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `raw_email_body` | string | Yes | The full raw text body of the AWS alert email |

## Extracted Fields
- `alarm_name` — Name of the CloudWatch alarm
- `new_state` — Current alarm state (ALARM, OK, INSUFFICIENT_DATA)
- `old_state` — Previous alarm state
- `reason` — Why the state changed
- `region` — AWS region
- `account_id` — AWS account ID
- `timestamp` — When the state changed
- `namespace` — CloudWatch metric namespace (e.g. AWS/EC2)
- `metric` — Metric name (e.g. CPUUtilization)
- `dimensions` — Metric dimensions (e.g. InstanceId)
- `threshold` — Alarm threshold value
- `comparison` — Comparison operator used

## When to Use
- When you receive an AWS alert email event
- When you need to understand what alarm fired, why, and where
- As a first step before fetching CloudWatch logs for investigation

## Example
```
Input:  Raw email body containing a JSON SNS alarm notification
Output: JSON with alarm_name="HighCPU", new_state="ALARM", region="ap-south-1", etc.
```
