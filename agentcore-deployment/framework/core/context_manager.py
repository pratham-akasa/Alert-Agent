"""
Context Manager — Maintains context from tool outputs to prevent hallucination.

This module tracks important values from tool outputs and provides them
to subsequent tool calls to prevent the LLM from changing values.
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manages context across tool calls to prevent value drift.
    
    Tracks key values like alarm_name, log_group, etc. from tool outputs
    and provides them for validation and correction.
    """
    
    def __init__(self):
        self.context: Dict[str, Any] = {}
        self._locked_values: Dict[str, str] = {}
        self._raw_outputs: Dict[str, str] = {}  # Store raw string outputs
    
    def _normalize_timestamp(self, timestamp: Any) -> Optional[str]:
        """
        Normalize timestamp to a consistent string format.
        
        Args:
            timestamp: Raw timestamp from parser (string, dict, or other)
            
        Returns:
            Normalized timestamp string or None if invalid
        """
        import re
        from datetime import datetime
        
        # Handle dict-like timestamp objects (e.g., {"$date": 1715248098000})
        if isinstance(timestamp, dict):
            if "$date" in timestamp:
                try:
                    # Convert milliseconds to seconds
                    timestamp_seconds = timestamp["$date"] / 1000
                    dt = datetime.fromtimestamp(timestamp_seconds)
                    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                except (ValueError, TypeError) as e:
                    logger.error("Failed to convert dict timestamp: %s", e)
                    return None
            else:
                logger.error("Unknown dict timestamp format: %s", timestamp)
                return None
        
        # Handle string timestamps
        if isinstance(timestamp, str):
            # Check if it's already a valid format
            if self._is_valid_timestamp_string(timestamp):
                return timestamp
            else:
                logger.error("Invalid timestamp string format: %s", timestamp)
                return None
        
        # Handle other types
        logger.error("Unsupported timestamp type: %s (%s)", type(timestamp), timestamp)
        return None
    
    def _is_valid_timestamp_string(self, timestamp_str: str) -> bool:
        """Check if timestamp string is in a valid format."""
        import re
        
        # AWS CloudWatch format: "Tuesday 10 March, 2026 04:08:18 UTC"
        aws_pattern = r'^[A-Za-z]+\s+\d{1,2}\s+[A-Za-z]+,\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+UTC$'
        
        # ISO format: "2026-03-10T04:08:18Z" or "2026-03-10T04:08:18+00:00"
        iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$'
        
        # Simple UTC format: "2026-03-10 04:08:18 UTC"
        simple_pattern = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+UTC$'
        
        return (re.match(aws_pattern, timestamp_str) or 
                re.match(iso_pattern, timestamp_str) or 
                re.match(simple_pattern, timestamp_str))

    def update_from_tool_output(self, tool_name: str, output: Any) -> None:
        """
        Update context from a tool output.
        
        Args:
            tool_name: Name of the tool that was called
            output: The tool's output (string or dict)
        """
        try:
            # Store raw output string for validation tool
            if isinstance(output, str):
                self._raw_outputs[tool_name] = output
                parsed_output = json.loads(output)
            else:
                # If it's already a dict, convert to JSON string for storage
                self._raw_outputs[tool_name] = json.dumps(output, default=str)
                parsed_output = output
            
            if tool_name == 'parse_aws_alert_email':
                alarm_name = parsed_output.get('alarm_name')
                if alarm_name:
                    self._locked_values['alarm_name'] = alarm_name
                    self.context['parsed_alarm_name'] = alarm_name
                    logger.info("🔒 Locked alarm_name: %s", alarm_name)
                
                timestamp = parsed_output.get('timestamp')
                if timestamp:
                    # Validate and normalize timestamp
                    normalized_timestamp = self._normalize_timestamp(timestamp)
                    if normalized_timestamp:
                        self._locked_values['alarm_timestamp'] = normalized_timestamp
                        self.context['parsed_timestamp'] = normalized_timestamp
                        logger.info("🔒 Locked alarm_timestamp: %s", normalized_timestamp)
                    else:
                        logger.error("❌ Invalid timestamp format: %s", timestamp)
                        # Don't lock invalid timestamps
            
            elif tool_name == 'discover_log_group':
                best_log_group = parsed_output.get('best_log_group')
                if best_log_group:
                    self._locked_values['log_group_name'] = best_log_group
                    self.context['discovered_log_group'] = best_log_group
                    logger.info("🔒 Locked log_group_name: %s", best_log_group)
            
            elif tool_name == 'fetch_cloudwatch_logs':
                # Store for validation
                self._locked_values['primary_logs_response'] = self._raw_outputs[tool_name]
                logger.info("🔒 Stored primary_logs_response (%d chars)", len(self._raw_outputs[tool_name]))
            
            elif tool_name == 'check_service_dependencies':
                # Store for validation
                self._locked_values['dependency_logs_response'] = self._raw_outputs[tool_name]
                logger.info("🔒 Stored dependency_logs_response (%d chars)", len(self._raw_outputs[tool_name]))
            
            # Store full output for reference
            self.context[f'{tool_name}_output'] = parsed_output
            
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Could not parse output for %s: %s", tool_name, e)
    
    def get_locked_value(self, key: str) -> Optional[str]:
        """Get a locked value that should not be changed."""
        return self._locked_values.get(key)
    
    def validate_and_correct_params(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parameters against locked context values and correct if needed.
        
        Args:
            tool_name: Name of the tool being called
            params: Parameters being passed to the tool
        
        Returns:
            Corrected parameters
        """
        logger.info("🔍 Validating params for tool: %s", tool_name)
        corrected = params.copy()
        corrections_made = []
        
        # AUTO-INJECT alarm_timestamp for time-sensitive tools if missing
        if tool_name in ['fetch_cloudwatch_logs', 'check_service_dependencies']:
            if not params.get('alarm_timestamp'):
                locked_timestamp = self.get_locked_value('alarm_timestamp')
                if locked_timestamp:
                    logger.warning("⚠️ AUTO-INJECTING alarm_timestamp for %s: %s", tool_name, locked_timestamp)
                    corrected['alarm_timestamp'] = locked_timestamp
                    corrections_made.append(f"alarm_timestamp: missing → {locked_timestamp}")
                else:
                    logger.error("❌ CRITICAL: No alarm_timestamp in context for %s!", tool_name)
            else:
                # Validate provided timestamp
                if not self._is_valid_timestamp_string(str(params['alarm_timestamp'])):
                    logger.error("❌ Invalid alarm_timestamp format for %s: %s", tool_name, params['alarm_timestamp'])
                    # Try to use locked timestamp instead
                    locked_timestamp = self.get_locked_value('alarm_timestamp')
                    if locked_timestamp:
                        logger.warning("⚠️ REPLACING invalid timestamp with locked value: %s", locked_timestamp)
                        corrected['alarm_timestamp'] = locked_timestamp
                        corrections_made.append(f"alarm_timestamp: invalid → {locked_timestamp}")
        
        # AUTO-INJECT log_group_name for fetch_cloudwatch_logs if missing
        if tool_name == 'fetch_cloudwatch_logs':
            if not params.get('log_group_name') and not params.get('log_group'):
                locked_log_group = self.get_locked_value('log_group_name')
                if locked_log_group:
                    logger.warning("⚠️ AUTO-INJECTING log_group_name: %s", locked_log_group)
                    corrected['log_group_name'] = locked_log_group
                    corrections_made.append(f"log_group_name: missing → {locked_log_group}")
        
        # Special handling for validate_investigation_logs
        if tool_name == 'validate_investigation_logs':
            logger.info("🎯 Special handling for validate_investigation_logs")
            
            # Auto-inject primary_logs_response if missing or empty
            if not params.get('primary_logs_response') or params.get('primary_logs_response') == '':
                primary_logs = self.get_locked_value('primary_logs_response')
                if primary_logs:
                    logger.warning("⚠️ AUTO-INJECTING primary_logs_response (%d chars)", len(primary_logs))
                    corrected['primary_logs_response'] = primary_logs
                    corrections_made.append("primary_logs_response: empty → injected from context")
                else:
                    logger.error("❌ No primary_logs_response in context!")
            else:
                logger.info("✅ primary_logs_response already provided")
            
            # Auto-inject dependency_logs_response if missing or empty
            if not params.get('dependency_logs_response') or params.get('dependency_logs_response') == '':
                dependency_logs = self.get_locked_value('dependency_logs_response')
                if dependency_logs:
                    logger.warning("⚠️ AUTO-INJECTING dependency_logs_response (%d chars)", len(dependency_logs))
                    corrected['dependency_logs_response'] = dependency_logs
                    corrections_made.append("dependency_logs_response: empty → injected from context")
                else:
                    logger.error("❌ No dependency_logs_response in context!")
            else:
                logger.info("✅ dependency_logs_response already provided")
            
            # Auto-inject alarm_timestamp if missing
            if not params.get('alarm_timestamp'):
                alarm_timestamp = self.get_locked_value('alarm_timestamp')
                if alarm_timestamp:
                    logger.warning("⚠️ AUTO-INJECTING alarm_timestamp: %s", alarm_timestamp)
                    corrected['alarm_timestamp'] = alarm_timestamp
                    corrections_made.append(f"alarm_timestamp: missing → {alarm_timestamp}")
            else:
                logger.info("✅ alarm_timestamp already provided")
        
        # Validate alarm_timestamp for time-sensitive tools
        if tool_name in ['fetch_cloudwatch_logs', 'check_service_dependencies']:
            alarm_timestamp = params.get('alarm_timestamp')
            if alarm_timestamp:
                if not self._is_valid_timestamp_string(str(alarm_timestamp)):
                    logger.error("❌ Invalid alarm_timestamp format for %s: %s", tool_name, alarm_timestamp)
                    # Don't allow invalid timestamps to proceed
                    corrected['alarm_timestamp'] = None
                    corrections_made.append(f"alarm_timestamp: invalid format → None (investigation will be marked incomplete)")
        
        # Validate alarm_name
        if 'alarm_name' in params:
            locked_alarm = self.get_locked_value('alarm_name')
            if locked_alarm and params['alarm_name'] != locked_alarm:
                logger.warning(
                    "⚠️ CORRECTING alarm_name: '%s' → '%s'",
                    params['alarm_name'],
                    locked_alarm
                )
                corrected['alarm_name'] = locked_alarm
                corrections_made.append(f"alarm_name: {params['alarm_name']} → {locked_alarm}")
        
        # Validate log_group_name — only for tools that use log_group_name, not notify_teams
        tools_with_log_group_name = {'fetch_cloudwatch_logs', 'discover_log_group', 'search_log_groups'}
        if tool_name in tools_with_log_group_name and ('log_group_name' in params or 'log_group' in params):
            locked_log_group = self.get_locked_value('log_group_name')
            
            # Fix parameter name if wrong
            if 'log_group' in params and 'log_group_name' not in params:
                logger.warning("⚠️ CORRECTING parameter name: 'log_group' → 'log_group_name'")
                corrected['log_group_name'] = params['log_group']
                del corrected['log_group']
                corrections_made.append("parameter name: log_group → log_group_name")
            
            # Fix value if wrong
            if locked_log_group:
                current_value = corrected.get('log_group_name') or corrected.get('log_group')
                if current_value and current_value != locked_log_group:
                    logger.warning(
                        "⚠️ CORRECTING log_group_name: '%s' → '%s'",
                        current_value,
                        locked_log_group
                    )
                    corrected['log_group_name'] = locked_log_group
                    if 'log_group' in corrected:
                        del corrected['log_group']
                    corrections_made.append(f"log_group_name: {current_value} → {locked_log_group}")
        
        if corrections_made:
            logger.info("✅ Made %d corrections for %s: %s", 
                       len(corrections_made), tool_name, corrections_made)
        else:
            logger.info("ℹ️ No corrections needed for %s", tool_name)
        
        return corrected
    
    def get_summary(self) -> str:
        """Get a summary of locked context values."""
        if not self._locked_values:
            return "No locked values yet"
        
        lines = ["Locked Context Values:"]
        for key, value in self._locked_values.items():
            lines.append(f"  - {key}: {value}")
        
        return "\n".join(lines)
    
    def clear(self) -> None:
        """Clear all context."""
        self.context.clear()
        self._locked_values.clear()
        logger.info("Context cleared")
