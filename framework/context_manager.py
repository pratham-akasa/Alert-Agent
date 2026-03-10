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
    
    def update_from_tool_output(self, tool_name: str, output: Any) -> None:
        """
        Update context from a tool output.
        
        Args:
            tool_name: Name of the tool that was called
            output: The tool's output (string or dict)
        """
        try:
            if isinstance(output, str):
                output = json.loads(output)
            
            if tool_name == 'parse_aws_alert_email':
                alarm_name = output.get('alarm_name')
                if alarm_name:
                    self._locked_values['alarm_name'] = alarm_name
                    self.context['parsed_alarm_name'] = alarm_name
                    logger.info("🔒 Locked alarm_name: %s", alarm_name)
                
                timestamp = output.get('timestamp')
                if timestamp:
                    self._locked_values['alarm_timestamp'] = timestamp
                    self.context['parsed_timestamp'] = timestamp
                    logger.info("🔒 Locked alarm_timestamp: %s", timestamp)
            
            elif tool_name == 'discover_log_group':
                best_log_group = output.get('best_log_group')
                if best_log_group:
                    self._locked_values['log_group_name'] = best_log_group
                    self.context['discovered_log_group'] = best_log_group
                    logger.info("🔒 Locked log_group_name: %s", best_log_group)
            
            # Store full output for reference
            self.context[f'{tool_name}_output'] = output
            
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
        corrected = params.copy()
        corrections_made = []
        
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
        
        # Validate log_group_name
        if 'log_group_name' in params or 'log_group' in params:
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
