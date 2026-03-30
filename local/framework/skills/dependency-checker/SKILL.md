---
name: dependency-checker
description: Check service dependencies and fetch their logs to find root causes during incident investigation. Use when analyzing impact, dependency chains, or probable blast radius after investigating the primary service.
compatibility: Designed for AWS service dependency investigation
allowed-tools: dependency_checker
metadata:
  owner: platform-team
  version: "1.0"
---

# Dependency Checker

## Purpose
Automatically check service dependencies and fetch their logs to find root causes during incident investigation.

## When to use
- **ALWAYS** use this tool after fetching logs from the primary service
- Use it BEFORE concluding your investigation
- When you need to understand if upstream/downstream services are causing issues
- When investigating cascading failures or dependency-related problems

## When not to use
- As the first step in investigation (parse email and check primary service first)
- When the primary service logs clearly show an internal issue with no external dependencies

## Required inputs
- `alarm_name` — The alarm name from the parsed email (e.g., "qp-booking-service-common-error")
- `alarm_timestamp` — The timestamp from the parsed alarm email
- Optional: `region` — AWS region (default: ap-south-1)

## Workflow
1. Ensure you have completed primary service investigation first
2. Call `dependency_checker` with the alarm name and timestamp from the parsed email
3. Review the comprehensive report showing all dependency logs and error counts
4. Use the results to determine if dependencies are the root cause

## Tool usage
- Call `dependency_checker` with the alarm name and timestamp
- **IMPORTANT**: Always pass the `alarm_timestamp` to ensure logs are fetched from the correct time window
- The tool does ALL the work automatically - you just call it once

## What it does automatically
1. Extracts the service name from the alarm
2. Looks up dependencies in the knowledge base
3. For EACH dependency:
   - Discovers the log group using Resource Explorer
   - Fetches recent ERROR logs from CloudWatch
4. Returns a comprehensive report with all dependency logs and error counts

## Edge cases
- No dependencies found: Tool will report no dependencies to check
- Dependency log groups not found: Tool will report discovery failures
- No errors in dependencies: Tool will show zero error counts
- Multiple dependencies with errors: Tool will provide comprehensive analysis

## Output expectations
Returns JSON with:
- List of all dependencies checked
- Log groups found for each dependency
- ERROR logs from each dependency (from the alarm time window)
- Summary with total errors found and analysis

## Examples

### Example 1: Finding dependency root cause
User request: Check if booking service errors are caused by dependencies
Action:
- Use `dependency_checker` with alarm_name="qp-booking-service-common-error" and alarm_timestamp
- Review dependency error counts to identify root cause

### Example 2: Comprehensive dependency analysis
After primary service investigation shows errors:
- Call `dependency_checker` to check all upstream/downstream services
- Compare error timing and counts to determine causation
- Use results in final investigation summary

## Important notes
- This tool is fully automated - no need to manually discover log groups or fetch logs
- It handles all dependencies in one call
- Dependencies often cause cascading failures
- If dependencies have errors, they are likely the root cause
- Always include dependency analysis in your investigation summary