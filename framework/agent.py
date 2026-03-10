"""
Agent — The core brain of the framework.

Uses LangChain's ReAct agent with ChatOllama to reason about events,
select and execute tools, and persist results to memory.
"""

import glob
import json
import logging
import os
import time
from typing import Optional

from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from framework.config import Config
from framework.memory import Memory
from framework.events.base import Event
from framework.conversation_logger import ConversationLogger

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AWS alert handler. You MUST respond ONLY in English language.

CRITICAL LANGUAGE RULE: 
- Write ALL responses in English
- Do NOT use Chinese, Japanese, Korean, or any other language
- If you start writing in another language, STOP and rewrite in English

Execute ALL steps automatically without asking for permission.

WORKFLOW (execute in order):
1. parse_aws_alert_email → Extract alarm_name and timestamp from email
2. discover_log_group(alarm_name=<alarm_name>) → Get best_log_group
3. fetch_cloudwatch_logs(log_group_name=<best_log_group>, filter_pattern="ERROR", minutes_back=10, alarm_timestamp=<timestamp>)
    CRITICAL: Use the EXACT log_group_name from step 2's "best_log_group" field
    CRITICAL: Use the timestamp from step 1's parse output as alarm_timestamp parameter
4. check_service_dependencies(alarm_name=<alarm_name>, alarm_timestamp=<timestamp>) - MANDATORY, automatically checks ALL dependencies
5. validate_investigation_logs(primary_logs_response=<step3_output>, dependency_logs_response=<step4_output>, alarm_timestamp=<timestamp>) - MANDATORY validation of ALL services
6. Analyze all logs (primary + dependencies) and provide summary IN ENGLISH ONLY

RULES:
- Execute all steps automatically - do NOT ask for permission
- Do NOT stop after discovering log groups - immediately fetch logs
- ALWAYS use the "best_log_group" value from discover_log_group output in step 3
- ALWAYS use the correct parameter name "log_group_name" for fetch_cloudwatch_logs
- ALWAYS pass the "timestamp" from parse_aws_alert_email as "alarm_timestamp" to fetch_cloudwatch_logs
- ALWAYS use the exact alarm_name from the email - do NOT change it
- ALWAYS call check_service_dependencies in step 4 with the alarm_timestamp - it automatically handles all dependencies
- ALWAYS call validate_investigation_logs in step 5 to validate ALL services (primary + dependencies)
- The dependency checker is fully automated - it discovers log groups and fetches logs for ALL dependencies
- The validation step is MANDATORY - it ensures all logs were fetched from correct time windows
- Only provide final summary after completing ALL steps including validation
- WRITE YOUR ENTIRE RESPONSE IN ENGLISH - NO EXCEPTIONS

## FINAL SUMMARY FORMAT (MANDATORY)

After completing all tool calls, you MUST provide a structured analysis following this EXACT format:

---
## 🔍 INVESTIGATION SUMMARY

### 1. WHERE IT HAPPENED
[List the specific services and log groups where errors occurred]
- Primary Service: [service name]
- Primary Log Group: [log group path]
- Affected Dependencies: [list any dependencies with errors]

### 2. WHAT HAPPENED
[Describe the specific error from the actual log messages]
- Error Type: [exact error type from logs]
- Error Message: [actual error message from logs]
- Error Count: [number of occurrences]
- Sample Error: [paste a sample error message]

### 3. WHY IT HAPPENED (Root Cause)
[Analyze the error to determine the root cause based on the actual error messages]
- Root Cause: [specific technical reason]
- Contributing Factors: [any additional factors]

### 4. POSSIBLE SOLUTIONS
[Provide 2-3 specific, actionable solutions]
1. [First solution with technical details]
2. [Second solution with technical details]
3. [Third solution with technical details]
---

CRITICAL RULES FOR SUMMARY:
- You MUST use the EXACT format above with the emoji and section headers
- You MUST extract actual error messages from the tool outputs
- You MUST NOT provide generic descriptions - use specific details from the logs
- You MUST analyze the actual error type (e.g., UnrecognizedPropertyException, TimeoutException, etc.)
- You MUST provide technical, actionable solutions based on the specific error

EXAMPLE OF GOOD SUMMARY:
---
## 🔍 INVESTIGATION SUMMARY

### 1. WHERE IT HAPPENED
- Identify the specific service(s) and log group(s) where errors occurred
- Include both primary service and any affected dependencies
- Example: "Errors occurred in data-transfer-service (/copilot/qp-prod-data-transfer-service)"

### 2. WHAT HAPPENED
- Describe the specific error from the log messages
- Extract the actual error type and message from the logs
- Example: "UnrecognizedPropertyException: Field 'DelayReasonCode.Custom' not recognized in DelayDetail class"

### 3. WHY IT HAPPENED (Root Cause)
- Analyze the error to determine the root cause
- Consider: data format issues, API changes, configuration problems, dependency failures
- Example: "The incoming data contains a field 'DelayReasonCode.Custom' that doesn't match the expected schema"

### 4. POSSIBLE SOLUTIONS
- Provide 2-3 actionable solutions
- Be specific and technical

DO NOT provide generic summaries. ALWAYS analyze the actual error messages from the logs.

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
    """
    Store a correction or learning about a specific alarm for future reference.

    Use this when a user tells you something was wrong with your analysis,
    or provides new operational knowledge about an alarm.

    Args:
        alarm_name: The alarm name this correction applies to (e.g. 'qp-booking-service-common-error').
        correction: The correction or new knowledge to remember (e.g. 'This alarm fires at 4 AM due to batch job — safe to ignore').

    Returns:
        Confirmation that the correction was stored.
    """
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
    """
    LangChain ReAct agent powered by Ollama.

    Workflow:
      1. Receive an Event
      2. Build prompt with event payload + memory context + corrections
      3. Run the ReAct loop (think → tool call → observe → repeat)
      4. Store the result in memory
      5. Notify the team via MS Teams
    """

    def __init__(self, config: Config, tools: list, memory: Memory):
        global _memory_ref
        self.config = config
        self.memory = memory
        _memory_ref = memory  # expose to the store_correction tool
        self.tools = tools + [store_correction]  # always include correction tool
        self.conv_logger = ConversationLogger(log_dir="logs")
        
        # Initialize context manager to prevent value drift
        from framework.context_manager import ContextManager
        self.context_manager = ContextManager()

        agent_cfg = config.agent_config
        self.max_iterations = agent_cfg.get("max_iterations", 10)
        self.verbose = agent_cfg.get("verbose", True)

        # ── LLM setup ─────────────────────────────────────────────
        self.llm = ChatOllama(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            temperature=0.2,
            timeout=300.0,  # 5 minutes timeout for slow local generation
        )

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
            "Agent initialized — model=%s, tools=%s, max_iter=%d",
            config.ollama_model,
            [t.name for t in self.tools],
            self.max_iterations,
        )

    def process_event(self, event: Event) -> str:
        """
        Process an event through the agent's reasoning loop.

        Returns the agent's final text response.
        """
        logger.info("Processing event: %s", event.summary)
        
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

            # Check if agent completed all required steps
            messages = result["messages"]
            tool_calls = [msg for msg in messages if hasattr(msg, 'tool_calls') and msg.tool_calls]
            tools_used = set()
            for msg in tool_calls:
                for tc in msg.tool_calls:
                    tools_used.add(tc.get('name', ''))
            
            # Required tools for alarm investigation
            required_tools = {'parse_aws_alert_email', 'discover_log_group', 'fetch_cloudwatch_logs', 'check_service_dependencies', 'validate_investigation_logs'}
            missing_tools = required_tools - tools_used
            
            if missing_tools and event.source == "email":
                logger.warning("Agent did not use required tools: %s", missing_tools)
                # Add context summary to help agent
                context_summary = self.context_manager.get_summary()
                follow_up = (
                    f"You have not completed the investigation. You MUST call these tools: {', '.join(missing_tools)}.\n"
                    f"{context_summary}\n"
                    f"Use the EXACT values from the context above. Continue now."
                )
                result = self.agent.invoke(
                    {"messages": messages + [("user", follow_up)]},
                    config={"recursion_limit": self.max_iterations},
                )
                # Update context again
                self._update_context_from_messages(result["messages"])

            # Extract the final AI message
            final_message = result["messages"][-1].content
            
            duration = time.time() - start_time
            logger.info("Agent response (%.1fs): %s", duration, final_message[:200])

            # Save conversation log
            log_path = self.conv_logger.save(
                event_source=event.source,
                event_type=event.event_type,
                user_message=user_message,
                messages=result["messages"],
                final_response=final_message,
                duration_seconds=duration,
            )
            logger.info("Conversation saved to: %s", log_path)

            # Store in memory
            self.memory.add_event(
                summary=f"Processed {event.source}/{event.event_type}: {final_message[:200]}",
                metadata={
                    "event_source": event.source,
                    "event_type": event.event_type,
                    "response_length": len(final_message),
                    "log_file": log_path,
                },
            )

            return final_message

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Agent error: {e}"
            logger.error(error_msg, exc_info=True)

            # Save error log too
            self.conv_logger.save(
                event_source=event.source,
                event_type=event.event_type,
                user_message=user_message,
                messages=[],
                final_response=f"**ERROR**: {error_msg}",
                duration_seconds=duration,
            )

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

    def process_text(self, text: str) -> str:
        """
        Process a plain text input (for manual / testing use).
        """
        event = Event(
            source="manual",
            event_type="user_input",
            payload={"text": text},
        )
        return self.process_event(event)

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

        if event.source == "email":
            parts.append(
                "\n=== INSTRUCTIONS ===\n"
                "Execute the full investigation workflow: parse → discover → fetch logs → check dependencies → analyze.\n"
                "CRITICAL: Write your ENTIRE response in ENGLISH language. Do NOT use Chinese or any other language.\n"
                "===================\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _load_skills() -> str:
        """Load all *_skill.md files from the tools directory."""
        skills_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "tools"
        )
        skill_files = glob.glob(os.path.join(skills_dir, "*_skill.md"))
        sections = []
        for path in sorted(skill_files):
            name = os.path.basename(path).replace("_skill.md", "")
            try:
                with open(path, "r") as f:
                    content = f.read()
                sections.append(f"### Skill: {name}\n{content}")
                logger.info("Loaded skill: %s", name)
            except Exception as e:
                logger.warning("Could not load skill %s: %s", path, e)
        return "\n---\n".join(sections) if sections else "No skill files found."
