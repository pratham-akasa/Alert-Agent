"""
Agent — The core brain of the framework (Lambda deployment version).

Uses LangChain's ReAct agent with ChatBedrock to reason about events,
select and execute tools, and persist results to memory in S3.
"""

import json
import logging
import os
import time
from typing import Optional

from langchain_core.tools import tool
from langchain_aws import ChatBedrock
from langgraph.prebuilt import create_react_agent

from framework.core.config import Config
from framework.core.memory import Memory
from framework.events.base import Event
from framework.core.conversation_logger import ConversationLogger

logger = logging.getLogger(__name__)

# ── System prompt (same as local version) ──────────────────────────────
SYSTEM_PROMPT = """You are an AWS alert handler. You MUST respond ONLY in English language.

**CRITICAL REFERENCE**: You have access to investigation_summary_skill.md which contains the MANDATORY format for investigation summaries. You MUST use this exact format for your final summary.

CRITICAL LANGUAGE RULE: 
- Write ALL responses in English
- Do NOT use Chinese, Japanese, Korean, or any other language
- If you start writing in another language, STOP and rewrite in English

**CRITICAL EMAIL BODY RULE:**
- You MUST use the EXACT email body from the event payload above
- The email body is in the JSON field "body" in the payload
- Do NOT generate fake email bodies with headers like "From: AWS Alerts <alerts@example.com>"
- Do NOT use test data like "BookingController.createBooking() throwing NullPointerException"
- Do NOT create example emails - use ONLY the real email body provided
- If you use any email body other than the exact one from the payload, the investigation will FAIL

Execute ALL steps automatically without asking for permission.

WORKFLOW (execute in order):
1. parse_aws_alert_email → Extract alarm_name and timestamp from email
    CRITICAL: Use the EXACT email body from the event payload above
    CRITICAL: Do NOT use placeholder text like "This is a sample email body"
    CRITICAL: Extract the "body" field from the JSON payload and pass it to parse_aws_alert_email
    CRITICAL: Save the "timestamp" field from the output - you MUST use it in steps 3 and 4
2. discover_log_group(alarm_name=<alarm_name>) → Get best_log_group
    CRITICAL: Save the "best_log_group" value - you MUST use it in step 3
3. fetch_cloudwatch_logs(log_group_name=<best_log_group>, filter_pattern="ERROR", minutes_back=10, alarm_timestamp=<timestamp>)
    CRITICAL: Use the EXACT log_group_name from step 2's "best_log_group" field
    CRITICAL: Use the timestamp from step 1's parse output as alarm_timestamp parameter
    CRITICAL: The alarm_timestamp parameter is MANDATORY - do NOT skip it
    CRITICAL: If you skip alarm_timestamp, you will investigate the WRONG time window
4. check_service_dependencies(alarm_name=<alarm_name>, alarm_timestamp=<timestamp>) - MANDATORY, automatically checks ALL dependencies
    CRITICAL: Use the SAME timestamp from step 1 as alarm_timestamp parameter
    CRITICAL: The alarm_timestamp parameter is MANDATORY - do NOT skip it
5. CREATE INVESTIGATION SUMMARY - **MANDATORY STEP**
6. notify_teams(summary=<investigation_summary>, alarm_name=<alarm_name>, log_group=<best_log_group>) - **MANDATORY FINAL STEP**

RULES:
- Execute all steps automatically - do NOT ask for permission
- Do NOT stop after discovering log groups - immediately fetch logs
- ALWAYS use the "best_log_group" value from discover_log_group output in step 3
- ALWAYS use the correct parameter name "log_group_name" for fetch_cloudwatch_logs
- ALWAYS pass the "timestamp" from parse_aws_alert_email as "alarm_timestamp" to fetch_cloudwatch_logs
- ALWAYS use the exact alarm_name from the email - do NOT change it
- ALWAYS call check_service_dependencies in step 4 with the alarm_timestamp - it automatically handles all dependencies
- ALWAYS call notify_teams in step 6 with the full investigation summary (do NOT pass severity — it is auto-inferred)
- The dependency checker is fully automated - it discovers log groups and fetches logs for ALL dependencies
- **MANDATORY**: You MUST complete ALL 6 steps before providing any final response
- **MANDATORY**: Your final response MUST use the exact investigation summary format from step 5
- Do NOT provide generic responses like "please provide the actual email body"
- Do NOT stop early with partial results
- If any step fails, continue with remaining steps and note failures in the summary
- WRITE YOUR ENTIRE RESPONSE IN ENGLISH - NO EXCEPTIONS

## Available Skills
{skills_context}

## Memory
{memory_context}

## Corrections
{corrections_context}
"""

# ── Module-level reference for the correction tool closure ───────────────
_memory_ref: Optional[Memory] = None


@tool
def store_correction(alarm_name: str, correction: str) -> str:
    """Store a correction or learning about a specific alarm for future reference."""
    if _memory_ref is None:
        return json.dumps({"error": "Memory not available"})

    _memory_ref.add_correction(alarm_name, correction)
    return json.dumps({
        "status": "stored",
        "alarm_name": alarm_name,
        "correction": correction,
        "message": f"Correction stored. I will apply this knowledge to future '{alarm_name}' alerts.",
    }, indent=2)


class Agent:
    """LangChain ReAct agent powered by Amazon Bedrock (Lambda deployment version)."""

    def __init__(self, config: Config, tools: list, memory: Memory):
        global _memory_ref
        self.config = config
        self.memory = memory
        _memory_ref = memory
        
        # Initialize context manager
        from framework.core.context_manager import ContextManager
        self.context_manager = ContextManager()
        
        # Wrap tools with context correction
        self.original_tools = tools
        self.tools = self._wrap_tools_with_context(tools) + [store_correction]
        
        # Use /tmp for Lambda logs (ephemeral)
        self.conv_logger = ConversationLogger(log_dir="/tmp/logs")

        agent_cfg = config.agent_config
        self.max_iterations = agent_cfg.get("max_iterations", 10)
        self.verbose = agent_cfg.get("verbose", True)

        # ── LLM setup (uses Lambda execution role) ────────────────
        bedrock_kwargs = {
            "model_id": config.bedrock_model_id,
            "region_name": config.bedrock_region,
            "model_kwargs": {"temperature": 0.2, "max_tokens": 4096},
        }
        self.llm = ChatBedrock(**bedrock_kwargs)

        # ── Load skill descriptions ─────────────────────────────────
        self.skills_context = self._load_skills()

        # ── Create ReAct agent via LangGraph ───────────────────────
        memory_context = self.memory.get_context_summary()

        # Build corrections context
        all_corrections = self.memory.get_all_corrections()
        if all_corrections:
            correction_lines = ["These are corrections from past investigations. ALWAYS apply them:"]
            for alarm, entries in all_corrections.items():
                latest = entries[-1]
                correction_lines.append(f"- **{alarm}**: {latest['correction']}")
            corrections_context = "\n".join(correction_lines)
        else:
            corrections_context = "No corrections stored yet."

        system_prompt = SYSTEM_PROMPT.format(
            skills_context=self.skills_context,
            memory_context=memory_context,
            corrections_context=corrections_context,
        )

        self.agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=system_prompt,
        )

        logger.info(
            "Agent initialized — model=%s (region=%s), tools=%s, max_iter=%d",
            config.bedrock_model_id,
            config.bedrock_region,
            [t.name for t in self.tools],
            self.max_iterations,
        )

    def process_event(self, event: Event) -> str:
        """Process an event through the agent's reasoning loop."""
        run_id = os.environ.get('AWS_REQUEST_ID', 'local')
        
        logger.info(json.dumps({
            "message": "event_processing_start",
            "meta": {
                "run_id": run_id,
                "source": event.source,
                "event_type": event.event_type
            }
        }))
        
        # Clear context for new event
        self.context_manager.clear()

        # Build the user message from the event
        user_message = self._format_event(event)

        # Run the agent
        start_time = time.time()
        try:
            result = self.agent.invoke(
                {"messages": [("user", user_message)]},
                config={"recursion_limit": self.max_iterations},
            )
            
            # Update context from tool outputs
            self._update_context_from_messages(result["messages"])

            # Extract the final AI message
            final_message = result["messages"][-1].content
            
            duration = time.time() - start_time
            logger.info(json.dumps({
                "message": "event_processing_complete",
                "meta": {
                    "run_id": run_id,
                    "duration_seconds": round(duration, 2),
                    "response_length": len(final_message)
                }
            }))

            # Save conversation log to /tmp (ephemeral)
            log_path = self.conv_logger.save(
                event_source=event.source,
                event_type=event.event_type,
                user_message=user_message,
                messages=result["messages"],
                final_response=final_message,
                duration_seconds=duration,
            )

            # Store in memory
            self.memory.add_event(
                summary=f"Processed {event.source}/{event.event_type}: {final_message[:200]}",
                metadata={
                    "event_source": event.source,
                    "event_type": event.event_type,
                    "response_length": len(final_message),
                    "log_file": log_path,
                    "run_id": run_id,
                },
            )

            return final_message

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Agent error: {e}"
            logger.error(json.dumps({
                "message": "event_processing_error",
                "meta": {
                    "run_id": run_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_seconds": round(duration, 2)
                }
            }), exc_info=True)

            self.memory.add_event(
                summary=f"Error processing {event.source}/{event.event_type}: {e}",
            )
            return error_msg
    
    def _update_context_from_messages(self, messages: list) -> None:
        """Update context manager from tool outputs in messages."""
        for msg in messages:
            if hasattr(msg, 'type') and msg.type == 'tool':
                tool_name = getattr(msg, 'name', '')
                content = getattr(msg, 'content', '')
                if tool_name:
                    self.context_manager.update_from_tool_output(tool_name, content)
    
    def _wrap_tools_with_context(self, tools: list):
        """Wrap tools to apply context corrections before execution."""
        from functools import wraps
        from langchain_core.tools import StructuredTool
        
        wrapped_tools = []
        for tool in tools:
            original_func = tool.func
            tool_name = tool.name
            
            @wraps(original_func)
            def wrapped_func(*args, _tool_name=tool_name, _original=original_func, **kwargs):
                corrected_kwargs = self.context_manager.validate_and_correct_params(_tool_name, kwargs)
                result = _original(*args, **corrected_kwargs)
                self.context_manager.update_from_tool_output(_tool_name, result)
                return result
            
            wrapped_tool = StructuredTool(
                name=tool.name,
                description=tool.description,
                func=wrapped_func,
                args_schema=tool.args_schema
            )
            wrapped_tools.append(wrapped_tool)
        
        return wrapped_tools

    @staticmethod
    def _format_event(event: Event) -> str:
        """Format an Event into a prompt string for the LLM."""
        parts = [
            f"## Incoming Event",
            f"- **Source**: {event.source}",
            f"- **Type**: {event.event_type}",
            f"- **Time**: {event.timestamp.isoformat()}",
            f"\n### Payload\n```json\n{json.dumps(event.payload, indent=2, default=str)}\n```",
        ]

        if event.source in ("email", "webhook", "sns"):
            parts.append(
                "\n=== INSTRUCTIONS ===\n"
                "Execute the full investigation workflow: parse → discover → fetch logs → check dependencies → analyze.\n"
                "CRITICAL: Write your ENTIRE response in ENGLISH language. Do NOT use Chinese or any other language.\n"
                "===================\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _load_skills() -> str:
        """Load all SKILL.md files from the skills directory."""
        # In Lambda, skills are packaged in the deployment
        skills_dir = os.path.join(os.path.dirname(__file__), "..", "skills")
        sections = []
        
        if os.path.exists(skills_dir):
            for skill_folder in sorted(os.listdir(skills_dir)):
                skill_path = os.path.join(skills_dir, skill_folder)
                if os.path.isdir(skill_path):
                    skill_file = os.path.join(skill_path, "SKILL.md")
                    if os.path.exists(skill_file):
                        try:
                            with open(skill_file, "r", encoding="utf-8", errors="replace") as f:
                                content = f.read()
                            sections.append(f"### Skill: {skill_folder}\n{content}")
                            logger.info("Loaded skill: %s", skill_folder)
                        except Exception as e:
                            logger.warning("Could not load skill %s: %s", skill_file, e)
        
        return "\n---\n".join(sections) if sections else "No skill files found."
