"""
AWS Bedrock AgentCore Runtime Entry Point

This is the main entry point for deploying the AWS Alert Bot to Amazon Bedrock AgentCore.
AgentCore handles the infrastructure, scaling, and invocation - you just provide the agent logic.

Usage:
    agentcore deploy --runtime-path agentcore_runtime.py --config agentcore_config.yaml
"""

import json
import logging
import os
from typing import Any, Dict

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from framework.core.config import Config
from framework.core.memory import Memory
from framework.core.agent import Agent
from framework.events.base import Event
from framework.tools.email_parser import parse_aws_alert_email
from framework.tools.cloudwatch_fetcher import fetch_cloudwatch_logs
from framework.tools.graph_email_tools import list_graph_emails, read_graph_email
from framework.tools.log_group_discovery import search_log_groups, discover_log_group
from framework.tools.dependency_checker import check_service_dependencies
from framework.tools.teams_notifier import notify_teams

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agentcore_runtime")

# Tool registry
ALL_TOOLS = [
    parse_aws_alert_email,
    fetch_cloudwatch_logs,
    discover_log_group,
    search_log_groups,
    check_service_dependencies,
    list_graph_emails,
    read_graph_email,
    notify_teams,
]

# Initialize AgentCore app
app = BedrockAgentCoreApp()

# Global agent instance (initialized on cold start)
_agent = None


def get_agent() -> Agent:
    """
    Lazy initialization of agent.
    Reuses the same agent instance across invocations (warm starts).
    """
    global _agent
    if _agent is None:
        logger.info("Initializing agent (cold start)...")
        config = Config(config_path="config.yaml")
        memory = Memory(filepath=config.agent_config.get("memory_file", "memory.json"))
        _agent = Agent(config=config, tools=ALL_TOOLS, memory=memory)
        logger.info("Agent initialized successfully")
    return _agent


@app.entrypoint
def handle_invocation(payload: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AgentCore invocation handler.
    
    Accepts two types of payloads:
    
    1. Email event (from EventBridge/polling):
       {
         "event": {
           "source": "graph_email",
           "event_type": "aws_alarm",
           "payload": {
             "subject": "ALARM: ...",
             "from": "...",
             "body": "..."
           }
         }
       }
    
    2. Interactive prompt:
       {
         "prompt": "Investigate alarm xyz"
       }
    
    Returns:
       {
         "statusCode": 200,
         "result": "Investigation summary..."
       }
    """
    logger.info("Received invocation with keys: %s", list(payload.keys()))
    
    try:
        agent = get_agent()
        
        # Parse input payload
        if "event" in payload:
            # Structured event input
            raw_event = payload["event"]
            event = Event(
                source=raw_event.get("source", "agentcore"),
                event_type=raw_event.get("event_type", "unknown"),
                payload=raw_event.get("payload", {}),
            )
            logger.info("Processing event: %s/%s", event.source, event.event_type)
        
        elif "prompt" in payload:
            # Interactive text input
            prompt = payload.get("prompt", "")
            event = Event(
                source="agentcore",
                event_type="user_input",
                payload={"text": prompt},
            )
            logger.info("Processing prompt: %s", prompt[:100])
        
        else:
            return {
                "statusCode": 400,
                "error": "Invalid payload. Expected 'event' or 'prompt' field."
            }
        
        # Process through agent
        result = agent.process_event(event)
        
        return {
            "statusCode": 200,
            "result": result
        }
    
    except Exception as e:
        logger.error("Error processing invocation: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "error": str(e)
        }


if __name__ == "__main__":
    # For local testing
    app.run()
