"""
Response Formatter — Ensures agent responses follow the required structure.

This module analyzes tool outputs and formats them into a structured summary
with WHERE, WHAT, WHY, and SOLUTIONS sections.
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Formats agent responses into structured summaries."""
    
    def __init__(self):
        self.parsed_data = {}
        self.log_data = {}
        self.dependency_data = {}
    
    def extract_tool_outputs(self, messages: List[Any]) -> None:
        """Extract and store outputs from tool calls in the conversation."""
        for msg in messages:
            # Check if this is a tool response message
            if hasattr(msg, 'type') and msg.type == 'tool':
                tool_name = getattr(msg, 'name', '')
                content = getattr(msg, 'content', '')
                
                try:
                    data = json.loads(content) if isinstance(content, str) else content
                    
                    if tool_name == 'parse_aws_alert_email':
                        self.parsed_data = data
                    elif tool_name == 'fetch_cloudwatch_logs':
                        self.log_data = data
                    elif tool_name == 'check_service_dependencies':
                        self.dependency_data = data
                        
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Could not parse tool output for %s: %s", tool_name, e)
    
    def _extract_error_details(self) -> Dict[str, Any]:
        """Extract error details from logs and dependencies."""
        errors = {
            'primary_service': None,
            'primary_log_group': None,
            'primary_errors': [],
            'dependency_errors': [],
            'total_errors': 0
        }
        
        # Extract primary service errors
        if self.log_data:
            errors['primary_log_group'] = self.log_data.get('log_group', '')
            errors['primary_errors'] = self.log_data.get('events', [])
            errors['total_errors'] += len(errors['primary_errors'])
        
        # Extract dependency errors
        if self.dependency_data:
            errors['primary_service'] = self.dependency_data.get('service_name', '')
            
            for dep in self.dependency_data.get('dependency_results', []):
                if dep.get('error_count', 0) > 0:
                    errors['dependency_errors'].append({
                        'name': dep.get('dependency_name', ''),
                        'log_group': dep.get('log_group', ''),
                        'error_count': dep.get('error_count', 0),
                        'errors': dep.get('errors', [])
                    })
                    errors['total_errors'] += dep.get('error_count', 0)
        
        return errors
    
    def _analyze_error_type(self, error_message: str) -> Dict[str, str]:
        """Analyze an error message to extract type and details."""
        analysis = {
            'type': 'Unknown Error',
            'details': error_message[:200],
            'class': None,
            'field': None
        }
        
        # Check for common error patterns
        if 'UnrecognizedPropertyException' in error_message:
            analysis['type'] = 'UnrecognizedPropertyException'
            
            # Extract field name
            field_match = re.search(r'Unrecognized field "([^"]+)"', error_message)
            if field_match:
                analysis['field'] = field_match.group(1)
            
            # Extract class name
            class_match = re.search(r'\(class ([^)]+)\)', error_message)
            if class_match:
                analysis['class'] = class_match.group(1)
            
            # Extract known properties
            props_match = re.search(r'known properties: "([^"]+)"', error_message)
            if props_match:
                analysis['known_properties'] = props_match.group(1)
        
        elif 'NullPointerException' in error_message:
            analysis['type'] = 'NullPointerException'
        
        elif 'TimeoutException' in error_message:
            analysis['type'] = 'TimeoutException'
        
        elif 'ConnectionException' in error_message or 'ConnectException' in error_message:
            analysis['type'] = 'Connection Error'
        
        elif 'SQLException' in error_message:
            analysis['type'] = 'Database Error'
        
        return analysis
    
    def _generate_where_section(self, errors: Dict[str, Any]) -> str:
        """Generate the WHERE IT HAPPENED section."""
        lines = ["### 1. WHERE IT HAPPENED\n"]
        
        if errors['primary_service']:
            lines.append(f"- **Primary Service**: {errors['primary_service']}")
        
        if errors['primary_log_group']:
            lines.append(f"- **Primary Log Group**: {errors['primary_log_group']}")
        
        if errors['dependency_errors']:
            lines.append(f"- **Affected Dependencies**:")
            for dep in errors['dependency_errors']:
                lines.append(f"  - {dep['name']} ({dep['log_group']}) - {dep['error_count']} errors")
        
        return "\n".join(lines)
    
    def _generate_what_section(self, errors: Dict[str, Any]) -> str:
        """Generate the WHAT HAPPENED section."""
        lines = ["### 2. WHAT HAPPENED\n"]
        
        # Analyze the most common error
        all_error_messages = []
        
        for dep in errors['dependency_errors']:
            for err in dep['errors'][:5]:  # Take first 5 errors
                all_error_messages.append(err.get('message', ''))
        
        for err in errors['primary_errors'][:5]:
            all_error_messages.append(err.get('message', ''))
        
        if all_error_messages:
            # Analyze the first error in detail
            first_error = all_error_messages[0]
            analysis = self._analyze_error_type(first_error)
            
            lines.append(f"- **Error Type**: {analysis['type']}")
            
            if analysis['field']:
                lines.append(f"- **Problematic Field**: `{analysis['field']}`")
            
            if analysis['class']:
                lines.append(f"- **Affected Class**: `{analysis['class']}`")
            
            if analysis.get('known_properties'):
                lines.append(f"- **Known Properties**: {analysis['known_properties']}")
            
            # Count occurrences
            lines.append(f"- **Error Count**: {errors['total_errors']} occurrences")
            
            # Show sample error
            lines.append(f"\n**Sample Error Message**:")
            lines.append(f"```\n{first_error[:400]}...\n```")
        else:
            lines.append("- No specific error messages found in logs")
        
        return "\n".join(lines)
    
    def _generate_why_section(self, errors: Dict[str, Any]) -> str:
        """Generate the WHY IT HAPPENED section."""
        lines = ["### 3. WHY IT HAPPENED (Root Cause)\n"]
        
        # Analyze based on error patterns
        all_error_messages = []
        for dep in errors['dependency_errors']:
            for err in dep['errors'][:3]:
                all_error_messages.append(err.get('message', ''))
        
        if all_error_messages:
            first_error = all_error_messages[0]
            analysis = self._analyze_error_type(first_error)
            
            if analysis['type'] == 'UnrecognizedPropertyException':
                lines.append(f"**Schema Mismatch Issue**")
                lines.append(f"- The incoming data contains a field `{analysis['field']}` that doesn't match the expected schema")
                lines.append(f"- The `{analysis['class']}` class is not configured to handle this field")
                lines.append(f"- This suggests either:")
                lines.append(f"  - The data source changed its format without updating the consumer")
                lines.append(f"  - The DTO class needs to be updated to handle new fields")
                lines.append(f"  - The field naming convention is incorrect (dotted notation like 'Field.Subfield')")
            
            elif analysis['type'] == 'Connection Error':
                lines.append("**Connectivity Issue**")
                lines.append("- The service cannot establish connection to a downstream dependency")
                lines.append("- This could be due to network issues, service downtime, or configuration problems")
            
            elif analysis['type'] == 'TimeoutException':
                lines.append("**Performance/Timeout Issue**")
                lines.append("- Requests are taking too long to complete")
                lines.append("- This could indicate database slowness, external API delays, or resource constraints")
            
            else:
                lines.append(f"**{analysis['type']}**")
                lines.append("- The error indicates a runtime issue that needs investigation")
        
        # Check if it's a dependency issue
        if errors['dependency_errors'] and not errors['primary_errors']:
            lines.append(f"\n**Cascading Failure**: The primary service alarm was triggered by failures in dependencies.")
        
        return "\n".join(lines)
    
    def _generate_solutions_section(self, errors: Dict[str, Any]) -> str:
        """Generate the POSSIBLE SOLUTIONS section."""
        lines = ["### 4. POSSIBLE SOLUTIONS\n"]
        
        # Analyze error type to provide specific solutions
        all_error_messages = []
        for dep in errors['dependency_errors']:
            for err in dep['errors'][:3]:
                all_error_messages.append(err.get('message', ''))
        
        if all_error_messages:
            first_error = all_error_messages[0]
            analysis = self._analyze_error_type(first_error)
            
            if analysis['type'] == 'UnrecognizedPropertyException':
                lines.append("**Immediate Actions:**")
                lines.append(f"1. **Add @JsonIgnoreProperties annotation**: Update the `{analysis['class']}` class with `@JsonIgnoreProperties(ignoreUnknown = true)` to ignore unexpected fields")
                lines.append(f"2. **Update the DTO schema**: Add the `{analysis['field']}` field to the `{analysis['class']}` class if it's a valid field")
                lines.append(f"3. **Validate data source**: Contact the team providing the data to verify the field naming convention")
                lines.append(f"\n**Long-term Solutions:**")
                lines.append(f"4. **Implement schema versioning**: Add API versioning to handle schema changes gracefully")
                lines.append(f"5. **Add monitoring**: Set up alerts for deserialization errors to catch schema mismatches early")
            
            elif analysis['type'] == 'Connection Error':
                lines.append("**Immediate Actions:**")
                lines.append("1. **Check service health**: Verify the downstream service is running and accessible")
                lines.append("2. **Review network configuration**: Check security groups, VPC settings, and DNS resolution")
                lines.append("3. **Verify credentials**: Ensure authentication tokens/credentials are valid")
                lines.append("\n**Long-term Solutions:**")
                lines.append("4. **Implement circuit breaker**: Add resilience patterns to handle downstream failures")
                lines.append("5. **Add retry logic**: Implement exponential backoff for transient failures")
            
            elif analysis['type'] == 'TimeoutException':
                lines.append("**Immediate Actions:**")
                lines.append("1. **Increase timeout values**: Temporarily increase timeout thresholds if appropriate")
                lines.append("2. **Check resource utilization**: Review CPU, memory, and database connection pools")
                lines.append("3. **Analyze slow queries**: Identify and optimize slow database queries or API calls")
                lines.append("\n**Long-term Solutions:**")
                lines.append("4. **Implement caching**: Add caching layer for frequently accessed data")
                lines.append("5. **Optimize performance**: Profile the application to identify bottlenecks")
            
            else:
                lines.append("**Recommended Actions:**")
                lines.append("1. **Review error logs**: Examine the full stack trace for more context")
                lines.append("2. **Check recent deployments**: Verify if recent code changes introduced this issue")
                lines.append("3. **Monitor error trends**: Track if the error rate is increasing or stable")
                lines.append("4. **Engage development team**: Escalate to the team responsible for the affected service")
        else:
            lines.append("**Recommended Actions:**")
            lines.append("1. **Investigate alarm configuration**: Verify the alarm threshold and metrics")
            lines.append("2. **Check service health**: Review service status and recent changes")
            lines.append("3. **Review monitoring data**: Examine CloudWatch metrics for anomalies")
        
        return "\n".join(lines)
    
    def format_response(self, messages: List[Any]) -> str:
        """
        Format the agent response into a structured summary.
        
        Args:
            messages: List of conversation messages including tool outputs
        
        Returns:
            Formatted response string with WHERE, WHAT, WHY, and SOLUTIONS sections
        """
        from framework.workflow_validator import WorkflowValidator
        
        # Validate workflow
        validator = WorkflowValidator()
        validation = validator.extract_and_validate_from_messages(messages)
        
        if not validation["workflow_valid"]:
            logger.warning("Workflow validation issues: %s", validation["issues"])
        
        # Extract tool outputs
        self.extract_tool_outputs(messages)
        
        # Check if we have enough data to format
        if not self.dependency_data and not self.log_data:
            logger.warning("No tool outputs found to format")
            # Return validation issues if workflow was incomplete
            if validation["issues"]:
                return self._format_workflow_error(validation)
            return None
        
        # Extract error details
        errors = self._extract_error_details()
        
        if errors['total_errors'] == 0:
            return self._format_no_errors_response(errors)
        
        # Generate structured sections
        sections = [
            "## 🔍 INVESTIGATION SUMMARY\n",
            self._generate_where_section(errors),
            "\n",
            self._generate_what_section(errors),
            "\n",
            self._generate_why_section(errors),
            "\n",
            self._generate_solutions_section(errors),
        ]
        
        # Add workflow warnings if any
        if validation["issues"]:
            sections.append("\n---\n")
            sections.append("### ⚠️ Workflow Warnings\n")
            for issue in validation["issues"]:
                sections.append(f"- {issue}\n")
        
        return "\n".join(sections)
    
    def _format_workflow_error(self, validation: Dict[str, Any]) -> str:
        """Format response when workflow validation fails."""
        lines = [
            "## ⚠️ INVESTIGATION INCOMPLETE\n",
            "The investigation workflow was not completed correctly.\n",
            "\n### Issues Detected:",
        ]
        
        for issue in validation["issues"]:
            lines.append(f"- {issue}")
        
        lines.append("\n### Tools Called:")
        for tool in validation["tools_called"]:
            lines.append(f"- {tool}")
        
        lines.append("\n### Required Workflow:")
        lines.append("1. parse_aws_alert_email")
        lines.append("2. discover_log_group")
        lines.append("3. fetch_cloudwatch_logs")
        lines.append("4. check_service_dependencies")
        
        return "\n".join(lines)
    
    def _format_no_errors_response(self, errors: Dict[str, Any]) -> str:
        """Format response when no errors are found."""
        lines = [
            "## 🔍 INVESTIGATION SUMMARY\n",
            "### Status: No Errors Found\n",
            f"- **Primary Service**: {errors.get('primary_service', 'Unknown')}",
            f"- **Log Group**: {errors.get('primary_log_group', 'Unknown')}",
            "\n**Analysis**: The alarm was triggered, but no ERROR logs were found in the recent time window.",
            "\n**Possible Reasons**:",
            "1. The error occurred outside the search window",
            "2. The alarm threshold may need adjustment",
            "3. The error was transient and has already resolved",
            "\n**Recommended Actions**:",
            "1. Expand the search time window to look further back",
            "2. Review the alarm configuration and threshold settings",
            "3. Check if the alarm state has returned to OK",
        ]
        return "\n".join(lines)
