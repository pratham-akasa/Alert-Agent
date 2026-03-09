"""
Workflow Validator — Validates that the agent is following the correct workflow.

This module provides validation to ensure the agent uses correct parameters
from previous tool outputs.
"""

import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class WorkflowValidator:
    """Validates agent workflow execution."""
    
    def __init__(self):
        self.tool_outputs: Dict[str, Any] = {}
    
    def record_tool_output(self, tool_name: str, output: Any) -> None:
        """Record a tool output for validation."""
        try:
            if isinstance(output, str):
                output = json.loads(output)
            self.tool_outputs[tool_name] = output
            logger.debug("Recorded output for tool: %s", tool_name)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Could not parse output for %s: %s", tool_name, e)
    
    def validate_fetch_logs_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate fetch_cloudwatch_logs parameters against discovered log group.
        
        Returns:
            Dict with validation result and corrected parameters if needed
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "corrected_params": None
        }
        
        # Check if discover_log_group was called
        if 'discover_log_group' not in self.tool_outputs:
            result["warnings"].append("discover_log_group was not called before fetch_cloudwatch_logs")
            return result
        
        discovery_output = self.tool_outputs['discover_log_group']
        best_log_group = discovery_output.get('best_log_group')
        
        if not best_log_group:
            result["warnings"].append("No best_log_group found in discovery output")
            return result
        
        # Check parameter name
        if 'log_group' in params and 'log_group_name' not in params:
            result["errors"].append("Wrong parameter name: use 'log_group_name' not 'log_group'")
            result["valid"] = False
            result["corrected_params"] = params.copy()
            result["corrected_params"]["log_group_name"] = params["log_group"]
            del result["corrected_params"]["log_group"]
        
        # Check if using the correct log group
        log_group_param = params.get('log_group_name') or params.get('log_group')
        
        if log_group_param and log_group_param != best_log_group:
            result["errors"].append(
                f"Wrong log group: using '{log_group_param}' but should use '{best_log_group}' from discovery"
            )
            result["valid"] = False
            if not result["corrected_params"]:
                result["corrected_params"] = params.copy()
            result["corrected_params"]["log_group_name"] = best_log_group
        
        return result
    
    def validate_dependency_check_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate check_service_dependencies parameters against parsed alarm.
        
        Returns:
            Dict with validation result and corrected parameters if needed
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "corrected_params": None
        }
        
        # Check if parse_aws_alert_email was called
        if 'parse_aws_alert_email' not in self.tool_outputs:
            result["warnings"].append("parse_aws_alert_email was not called before check_service_dependencies")
            return result
        
        parse_output = self.tool_outputs['parse_aws_alert_email']
        correct_alarm_name = parse_output.get('alarm_name')
        
        if not correct_alarm_name:
            result["warnings"].append("No alarm_name found in parse output")
            return result
        
        # Check if using the correct alarm name
        alarm_name_param = params.get('alarm_name')
        
        if alarm_name_param and alarm_name_param != correct_alarm_name:
            result["errors"].append(
                f"Wrong alarm name: using '{alarm_name_param}' but should use '{correct_alarm_name}' from parsing"
            )
            result["valid"] = False
            result["corrected_params"] = params.copy()
            result["corrected_params"]["alarm_name"] = correct_alarm_name
        
        return result
    
    def extract_and_validate_from_messages(self, messages: List[Any]) -> Dict[str, Any]:
        """
        Extract tool outputs from messages and validate the workflow.
        
        Returns:
            Dict with validation summary
        """
        validation_summary = {
            "workflow_valid": True,
            "issues": [],
            "tools_called": []
        }
        
        # Extract tool outputs
        for msg in messages:
            if hasattr(msg, 'type') and msg.type == 'tool':
                tool_name = getattr(msg, 'name', '')
                content = getattr(msg, 'content', '')
                
                if tool_name:
                    validation_summary["tools_called"].append(tool_name)
                    self.record_tool_output(tool_name, content)
        
        # Check workflow order
        expected_order = [
            'parse_aws_alert_email',
            'discover_log_group',
            'fetch_cloudwatch_logs',
            'check_service_dependencies'
        ]
        
        tools_called = validation_summary["tools_called"]
        
        for i, expected_tool in enumerate(expected_order):
            if expected_tool not in tools_called:
                validation_summary["issues"].append(f"Missing required tool: {expected_tool}")
                validation_summary["workflow_valid"] = False
            elif i > 0:
                # Check if previous tool was called before this one
                prev_tool = expected_order[i-1]
                if prev_tool in tools_called and expected_tool in tools_called:
                    prev_idx = tools_called.index(prev_tool)
                    curr_idx = tools_called.index(expected_tool)
                    if curr_idx < prev_idx:
                        validation_summary["issues"].append(
                            f"Wrong order: {expected_tool} called before {prev_tool}"
                        )
                        validation_summary["workflow_valid"] = False
        
        return validation_summary
