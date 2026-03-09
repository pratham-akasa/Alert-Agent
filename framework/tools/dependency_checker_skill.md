# Skill: Dependency Checker

## Purpose
Automatically check service dependencies and fetch their logs to find root causes.

## When to Use
- **ALWAYS** use this tool after fetching logs from the primary service
- Use it BEFORE concluding your investigation
- This tool does ALL the work automatically - you just call it once

## How to Use
```python
check_service_dependencies(alarm_name="qp-booking-service-common-error", region="ap-south-1")
```

## What It Does Automatically
1. Extracts the service name from the alarm
2. Looks up dependencies in the knowledge base
3. For EACH dependency:
   - Discovers the log group using Resource Explorer
   - Fetches recent ERROR logs from CloudWatch
4. Returns a comprehensive report with all dependency logs and error counts

## Output
Returns JSON with:
- List of all dependencies checked
- Log groups found for each dependency
- ERROR logs from each dependency (last 10 minutes)
- Summary: total errors found and analysis

## Example
```python
# Just call it once with the alarm name
check_service_dependencies(alarm_name="qp-booking-service-common-error")

# Returns:
# {
#   "status": "completed",
#   "dependencies_checked": 2,
#   "dependency_results": [
#     {
#       "dependency_name": "NavOds-Webservice",
#       "log_group": "/copilot/qp-prod-navods-webservice",
#       "error_count": 15,
#       "errors": [...]
#     },
#     {
#       "dependency_name": "data-transfer-service",
#       "log_group": "/copilot/qp-prod-data-transfer-service",
#       "error_count": 0,
#       "errors": []
#     }
#   ],
#   "summary": {
#     "total_dependency_errors": 15,
#     "analysis": "Found 15 ERROR logs across 2 dependencies. Root cause likely in dependencies."
#   }
# }
```

## Important
- This tool is fully automated - no need to manually discover log groups or fetch logs
- It handles all dependencies in one call
- Dependencies often cause cascading failures
- If dependencies have errors, they are likely the root cause
