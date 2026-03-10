"""
Tool: Comprehensive Log Validation

Validates ALL log fetches in an investigation - primary service and all dependencies.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def validate_investigation_logs(
    primary_logs_response: str,
    dependency_logs_response: str,
    alarm_timestamp: str,
    expected_minutes_back: int = 10
) -> str:
    """
    Comprehensive validation of ALL log fetches in an investigation.
    
    Validates both primary service logs and all dependency logs to ensure:
    - All logs were fetched from alarm time (not current time)
    - Time windows are correct for all services
    - Timestamps are consistent across all log fetches
    
    Args:
        primary_logs_response: JSON response from fetch_cloudwatch_logs for primary service
        dependency_logs_response: JSON response from check_service_dependencies
        alarm_timestamp: The original alarm timestamp from parse_aws_alert_email
        expected_minutes_back: Expected minutes back from alarm time (default 10)
    
    Returns:
        Comprehensive validation report for all services with pass/fail status
    """
    try:
        # Parse alarm timestamp
        alarm_time = _parse_alarm_timestamp(alarm_timestamp)
        if not alarm_time:
            return json.dumps({
                "status": "error",
                "message": "Could not parse alarm timestamp",
                "alarm_timestamp": alarm_timestamp
            }, indent=2)
        
        # Expected time window
        expected_end = alarm_time
        expected_start = alarm_time - timedelta(minutes=expected_minutes_back)
        
        validation_report = {
            "status": "validated",
            "alarm_timestamp": alarm_timestamp,
            "expected_window": f"{expected_start.isoformat()} → {expected_end.isoformat()}",
            "overall_pass": True,
            "services_validated": [],
            "summary": {}
        }
        
        # Validate primary service logs
        try:
            primary_data = json.loads(primary_logs_response) if isinstance(primary_logs_response, str) else primary_logs_response
            primary_validation = _validate_single_service_logs(
                service_name="Primary Service",
                log_data=primary_data,
                expected_start=expected_start,
                expected_end=expected_end,
                alarm_timestamp=alarm_timestamp
            )
            validation_report["services_validated"].append(primary_validation)
            
            if not primary_validation.get("overall_pass", False):
                validation_report["overall_pass"] = False
                
        except Exception as e:
            logger.error("Error validating primary logs: %s", e)
            validation_report["services_validated"].append({
                "service_name": "Primary Service",
                "validation_error": str(e),
                "overall_pass": False
            })
            validation_report["overall_pass"] = False
        
        # Validate dependency logs
        try:
            dependency_data = json.loads(dependency_logs_response) if isinstance(dependency_logs_response, str) else dependency_logs_response
            
            if "dependency_results" in dependency_data:
                for dep in dependency_data["dependency_results"]:
                    dep_validation = _validate_single_service_logs(
                        service_name=f"Dependency: {dep.get('dependency_name', 'Unknown')}",
                        log_data=dep,
                        expected_start=expected_start,
                        expected_end=expected_end,
                        alarm_timestamp=alarm_timestamp
                    )
                    validation_report["services_validated"].append(dep_validation)
                    
                    if not dep_validation.get("overall_pass", False):
                        validation_report["overall_pass"] = False
            else:
                validation_report["services_validated"].append({
                    "service_name": "Dependencies",
                    "validation_error": "No dependency_results found in response",
                    "overall_pass": False
                })
                validation_report["overall_pass"] = False
                
        except Exception as e:
            logger.error("Error validating dependency logs: %s", e)
            validation_report["services_validated"].append({
                "service_name": "Dependencies",
                "validation_error": str(e),
                "overall_pass": False
            })
            validation_report["overall_pass"] = False
        
        # Generate summary
        total_services = len(validation_report["services_validated"])
        passed_services = sum(1 for s in validation_report["services_validated"] if s.get("overall_pass", False))
        failed_services = total_services - passed_services
        
        validation_report["summary"] = {
            "total_services_checked": total_services,
            "services_passed": passed_services,
            "services_failed": failed_services,
            "validation_success_rate": f"{(passed_services/total_services*100):.1f}%" if total_services > 0 else "0%",
            "critical_issues": _extract_critical_issues(validation_report["services_validated"])
        }
        
        return json.dumps(validation_report, indent=2, default=str)
        
    except Exception as e:
        logger.error("Comprehensive validation failed: %s", e)
        return json.dumps({
            "status": "error",
            "message": str(e),
            "alarm_timestamp": alarm_timestamp
        }, indent=2)

def _parse_alarm_timestamp(alarm_timestamp: str) -> datetime:
    """Parse alarm timestamp from various formats."""
    for fmt in [
        "%A %d %B, %Y %H:%M:%S %Z",  # "Monday 09 March, 2026 04:08:18 UTC"
        "%Y-%m-%dT%H:%M:%S%z",        # ISO format with timezone
        "%Y-%m-%d %H:%M:%S",          # Simple format
    ]:
        try:
            alarm_time = datetime.strptime(alarm_timestamp, fmt)
            if alarm_time.tzinfo is None:
                alarm_time = alarm_time.replace(tzinfo=timezone.utc)
            return alarm_time
        except ValueError:
            continue
    return None

def _validate_single_service_logs(service_name: str, log_data: dict, expected_start: datetime, expected_end: datetime, alarm_timestamp: str) -> dict:
    """Validate logs for a single service."""
    
    validation = {
        "service_name": service_name,
        "log_group": log_data.get("log_group"),
        "checks": {},
        "overall_pass": True,
        "issues": []
    }
    
    # Check if alarm timestamp was used
    alarm_timestamp_used = log_data.get("alarm_timestamp_used", "")
    timestamp_check = {
        "pass": alarm_timestamp_used != "current time" and alarm_timestamp_used == alarm_timestamp,
        "expected": alarm_timestamp,
        "actual": alarm_timestamp_used
    }
    validation["checks"]["used_alarm_timestamp"] = timestamp_check
    
    if not timestamp_check["pass"]:
        validation["overall_pass"] = False
        if alarm_timestamp_used == "current time":
            validation["issues"].append("❌ CRITICAL: Used current time instead of alarm timestamp")
        else:
            validation["issues"].append(f"❌ Timestamp mismatch: expected '{alarm_timestamp}', got '{alarm_timestamp_used}'")
    
    # Parse and validate time range
    time_range = log_data.get("time_range", "")
    if "→" in time_range:
        try:
            start_str, end_str = time_range.split("→")
            actual_start = datetime.fromisoformat(start_str.strip().replace('Z', '+00:00'))
            actual_end = datetime.fromisoformat(end_str.strip().replace('Z', '+00:00'))
            
            validation["actual_window"] = f"{actual_start.isoformat()} → {actual_end.isoformat()}"
            
            # Check end time (should match alarm time within 1 minute)
            end_diff = abs((actual_end - expected_end).total_seconds())
            end_time_check = {
                "pass": end_diff <= 60,
                "expected": expected_end.isoformat(),
                "actual": actual_end.isoformat(),
                "diff_seconds": end_diff
            }
            validation["checks"]["end_time_correct"] = end_time_check
            
            if not end_time_check["pass"]:
                validation["overall_pass"] = False
                validation["issues"].append(f"❌ End time off by {end_diff:.0f} seconds from alarm time")
            
            # Check start time
            start_diff = abs((actual_start - expected_start).total_seconds())
            start_time_check = {
                "pass": start_diff <= 60,
                "expected": expected_start.isoformat(),
                "actual": actual_start.isoformat(),
                "diff_seconds": start_diff
            }
            validation["checks"]["start_time_correct"] = start_time_check
            
            if not start_time_check["pass"]:
                validation["overall_pass"] = False
                validation["issues"].append(f"❌ Start time off by {start_diff:.0f} seconds from expected")
            
        except Exception as e:
            validation["checks"]["time_parsing"] = {
                "pass": False,
                "error": str(e),
                "time_range": time_range
            }
            validation["overall_pass"] = False
            validation["issues"].append(f"❌ Could not parse time range: {e}")
    else:
        validation["checks"]["time_range_format"] = {
            "pass": False,
            "message": "Could not parse time_range",
            "time_range": time_range
        }
        validation["overall_pass"] = False
        validation["issues"].append("❌ Invalid time range format")
    
    # Check event count and log quality
    event_count = log_data.get("event_count", 0)
    validation["checks"]["log_fetch_success"] = {
        "pass": True,  # Having 0 events is not necessarily wrong
        "event_count": event_count,
        "note": "0 events may be normal if no errors occurred in the time window"
    }
    
    # Add success indicators
    if validation["overall_pass"]:
        validation["issues"].append("✅ All validations passed")
    
    return validation

def _extract_critical_issues(service_validations: list) -> list:
    """Extract critical issues across all services."""
    critical_issues = []
    
    for service in service_validations:
        service_name = service.get("service_name", "Unknown")
        issues = service.get("issues", [])
        
        for issue in issues:
            if "❌ CRITICAL" in issue or "current time" in issue:
                critical_issues.append(f"{service_name}: {issue}")
    
    return critical_issues

if __name__ == "__main__":
    # Test validation
    sample_primary = {
        "log_group": "/copilot/qp-prod-qp-booking-webservice",
        "time_range": "2026-03-09T03:58:18+00:00 → 2026-03-09T04:08:18+00:00",
        "alarm_timestamp_used": "Monday 09 March, 2026 04:08:18 UTC",
        "event_count": 0
    }
    
    sample_dependencies = {
        "dependency_results": [
            {
                "dependency_name": "data-transfer-service",
                "log_group": "/copilot/qp-prod-data-transfer-service",
                "time_range": "2026-03-09T03:58:18+00:00 → 2026-03-09T04:08:18+00:00",
                "alarm_timestamp_used": "Monday 09 March, 2026 04:08:18 UTC",
                "event_count": 50
            }
        ]
    }
    
    result = validate_investigation_logs(
        json.dumps(sample_primary),
        json.dumps(sample_dependencies),
        "Monday 09 March, 2026 04:08:18 UTC"
    )
    
    print(result)