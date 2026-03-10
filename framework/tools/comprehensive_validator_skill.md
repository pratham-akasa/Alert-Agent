# Skill: Comprehensive Log Validation

## Purpose
Validates ALL log fetches in an investigation - both primary service and all dependencies - to ensure logs were fetched from the correct time windows.

## When to Use
- **ALWAYS** use this tool after completing steps 3 and 4 (fetch_cloudwatch_logs and check_service_dependencies)
- Use it BEFORE providing your final analysis
- This is step 5 in the mandatory investigation workflow

## How to Use
```python
validate_investigation_logs(
    primary_logs_response=<output_from_fetch_cloudwatch_logs>,
    dependency_logs_response=<output_from_check_service_dependencies>,
    alarm_timestamp="Monday 09 March, 2026 04:08:18 UTC",
    expected_minutes_back=10
)
```

**CRITICAL**: You MUST pass the exact JSON outputs from steps 3 and 4 as parameters.

## What It Validates
For EVERY service (primary + all dependencies):
1. **Timestamp Source**: Ensures alarm timestamp was used (not "current time")
2. **Time Window**: Validates start/end times match alarm time ± minutes_back
3. **Time Range Format**: Checks time range parsing and format
4. **Log Fetch Success**: Verifies logs were successfully retrieved

## Output
Returns comprehensive validation report with:
- **Overall Pass/Fail**: Whether ALL services passed validation
- **Per-Service Results**: Detailed validation for each service
- **Critical Issues**: List of serious problems (e.g., using current time)
- **Summary Statistics**: Success rate across all services

## Example Output
```json
{
  "status": "validated",
  "overall_pass": false,
  "services_validated": [
    {
      "service_name": "Primary Service",
      "log_group": "/copilot/qp-prod-qp-booking-webservice",
      "overall_pass": false,
      "issues": [
        "❌ CRITICAL: Used current time instead of alarm timestamp"
      ]
    },
    {
      "service_name": "Dependency: data-transfer-service",
      "log_group": "/copilot/qp-prod-data-transfer-service",
      "overall_pass": true,
      "issues": [
        "✅ All validations passed"
      ]
    }
  ],
  "summary": {
    "total_services_checked": 3,
    "services_passed": 2,
    "services_failed": 1,
    "validation_success_rate": "66.7%",
    "critical_issues": [
      "Primary Service: ❌ CRITICAL: Used current time instead of alarm timestamp"
    ]
  }
}
```

## Critical Issues to Watch For
- **❌ CRITICAL: Used current time instead of alarm timestamp**
- **❌ End time off by X seconds from alarm time**
- **❌ Could not parse time range**
- **❌ Timestamp mismatch**

## Integration with Analysis
Use validation results in your final analysis:

```
If validation fails:
- Mention which services had validation issues
- Note that log timing may be incorrect
- Recommend re-running investigation with proper timestamps

If validation passes:
- Proceed with confidence in log analysis
- All services were checked at the correct time window
```

## Workflow Position
```
1. parse_aws_alert_email ✅
2. discover_log_group ✅  
3. fetch_cloudwatch_logs ✅
4. check_service_dependencies ✅
5. validate_investigation_logs ← YOU ARE HERE
6. Provide final analysis
```

## Important Notes
- This tool validates ALL services in one call
- It's the only way to ensure comprehensive validation
- Validation failures indicate serious timing issues
- Always include validation results in your analysis
- If validation fails, the investigation may need to be re-run

## Example Usage in Investigation
```python
# After completing log fetching steps
validation_result = validate_investigation_logs(
    primary_logs_response=primary_logs_json,
    dependency_logs_response=dependency_logs_json,
    alarm_timestamp=parsed_timestamp
)

# Check validation in your analysis
if validation_result["overall_pass"]:
    # Proceed with log analysis
    print("✅ All services validated - logs are from correct time window")
else:
    # Note validation issues
    print("❌ Validation issues found - some logs may be from wrong time window")
    print("Critical issues:", validation_result["summary"]["critical_issues"])
```