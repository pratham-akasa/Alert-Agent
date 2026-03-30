"""
AWS Bedrock AgentCore Runtime Entry Point

This is the entry point for AgentCore deployment. It handles:
- Loading memory from S3
- Processing events through the agent
- Saving memory back to S3
- Structured CloudWatch logging

Flow:
  Trigger → AgentCore → Load memory (S3) → Run agent → Log to CloudWatch → Save memory (S3) → Return result
"""

import json
import logging
import os
import time
from typing import Any, Dict

# AgentCore imports (REQUIRED)
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Framework imports
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

# Configure structured logging for CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("agentcore_runtime")

# Initialize AgentCore app (REQUIRED)
app = BedrockAgentCoreApp()

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

# Global agent instance (reused across warm starts)
_agent = None
_config = None


def get_config() -> Config:
    """
    Load configuration from environment variables.
    This replaces config.yaml for Lambda deployment.
    """
    global _config
    if _config is None:
        logger.info("Loading configuration from environment variables")
        _config = Config.from_env()
    return _config


def get_agent() -> Agent:
    """
    Lazy initialization of agent.
    Reuses the same agent instance across invocations (warm starts).
    """
    global _agent
    if _agent is None:
        run_id = 'init'
        logger.info(json.dumps({
            "message": "agent_init_start",
            "meta": {"run_id": run_id, "cold_start": True}
        }))
        
        config = get_config()
        memory = Memory.from_s3(
            bucket=os.environ.get('MEMORY_BUCKET'),
            key=os.environ.get('MEMORY_KEY', 'memory.json')
        )
        _agent = Agent(config=config, tools=ALL_TOOLS, memory=memory)
        
        logger.info(json.dumps({
            "message": "agent_init_complete",
            "meta": {"run_id": run_id, "tools": [t.name for t in ALL_TOOLS]}
        }))
    return _agent


@app.entrypoint
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AgentCore entrypoint handler (REQUIRED decorator).
    
    Accepts multiple event types:
    
    1. Email webhook (from API Gateway or SNS):
       {
         "body": "{...email payload...}"
       }
    
    2. CloudWatch Alarm (from SNS):
       {
         "Records": [{
           "Sns": {
             "Message": "..."
           }
         }]
       }
    
    3. Direct event:
       {
         "event": {
           "source": "email",
           "event_type": "aws_alarm",
           "payload": {...}
         }
       }
    
    Returns:
       {
         "statusCode": 200,
         "body": "investigation summary..."
       }
    """
    start_time = time.time()
    # AgentCore context has different attributes than Lambda context
    run_id = getattr(context, 'request_id', None) or os.environ.get('AWS_REQUEST_ID', 'local')
    
    logger.info(json.dumps({
        "message": "lambda_invocation_start",
        "meta": {
            "run_id": run_id,
            "event_keys": list(event.keys())
        }
    }))
    
    try:
        # Parse input event
        agent_event = parse_lambda_event(event)
        
        logger.info(json.dumps({
            "message": "event_parsed",
            "meta": {
                "run_id": run_id,
                "source": agent_event.source,
                "event_type": agent_event.event_type
            }
        }))
        
        # Get agent (loads memory from S3 on cold start)
        agent = get_agent()
        
        # Process through agent
        logger.info(json.dumps({
            "message": "agent_execution_start",
            "meta": {"run_id": run_id}
        }))
        
        result = agent.process_event(agent_event)
        
        duration = time.time() - start_time
        logger.info(json.dumps({
            "message": "agent_execution_complete",
            "meta": {
                "run_id": run_id,
                "duration_seconds": round(duration, 2),
                "result_length": len(result)
            }
        }))
        
        # Save memory back to S3
        logger.info(json.dumps({
            "message": "memory_save_start",
            "meta": {"run_id": run_id}
        }))
        
        agent.memory.save_to_s3()
        
        logger.info(json.dumps({
            "message": "memory_save_complete",
            "meta": {"run_id": run_id}
        }))
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Investigation complete",
                "result": result,
                "duration_seconds": round(duration, 2)
            })
        }
    
    except Exception as e:
        duration = time.time() - start_time
        logger.error(json.dumps({
            "message": "lambda_error",
            "meta": {
                "run_id": run_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_seconds": round(duration, 2)
            }
        }), exc_info=True)
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "error_type": type(e).__name__
            })
        }


def parse_lambda_event(event: Dict[str, Any]) -> Event:
    """
    Parse various Lambda event formats into our Event object.
    """
    # Direct event format
    if "event" in event:
        raw_event = event["event"]
        return Event(
            source=raw_event.get("source", "lambda"),
            event_type=raw_event.get("event_type", "unknown"),
            payload=raw_event.get("payload", {}),
        )
    
    # SNS event (CloudWatch Alarm)
    if "Records" in event and event["Records"]:
        record = event["Records"][0]
        if "Sns" in record:
            sns_message = record["Sns"]["Message"]
            return Event(
                source="sns",
                event_type="aws_alarm",
                payload={"body": sns_message},
            )
    
    # API Gateway event (webhook)
    if "body" in event:
        body = event["body"]
        if isinstance(body, str):
            body = json.loads(body)
        
        return Event(
            source="webhook",
            event_type="email",
            payload=body,
        )
    
    # Fallback: treat entire event as payload
    return Event(
        source="lambda",
        event_type="unknown",
        payload=event,
    )


# For local testing with AgentCore
if __name__ == "__main__":
    app.run()
