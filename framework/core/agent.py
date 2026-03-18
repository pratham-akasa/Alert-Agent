"""
Agent — The core brain of the framework.

Uses LangChain's ReAct agent with ChatBedrock to reason about events,
select and execute tools, and persist results to memory.
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

# ── System prompt ──────────────────────────────────────────────────────

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
   - **YOU MUST USE THIS EXACT FORMAT:**
   ```
   ---
   ## 🔍 INVESTIGATION SUMMARY

   ### 1. WHERE IT HAPPENED
   - Primary Service: [extract from discover_log_group output]
   - Primary Log Group: [extract from discover_log_group output]
   - Affected Dependencies: [extract from check_service_dependencies output]

   ### 2. WHAT HAPPENED
   - Error Type: [extract from actual log messages OR "No errors found" if event_count = 0]
   - Error Message: [copy exact error from logs OR "N/A" if event_count = 0]
   - Error Count: [extract from tool outputs - use the ACTUAL number]
   - Sample Error: [paste actual error message OR "N/A" if event_count = 0]

   ### 3. WHY IT HAPPENED (Root Cause)
   - Root Cause: [analyze the specific error type OR explain why no errors were found]
   - Contributing Factors: [additional factors]

   ### 4. POSSIBLE SOLUTIONS
   1. [Technical solution based on error type OR investigation steps if no errors found]
   2. [Second technical solution]
   3. [Third technical solution if applicable]
   ---
   ```
   - **EXTRACT real data** from your tool outputs (steps 1-4)
   - **CRITICAL: Check event_count in fetch_cloudwatch_logs output**
   - **If event_count = 0 and events = [], you MUST report "No errors found" - DO NOT make up fake errors**
   - **NEVER make up information** - use actual data from tool responses

RULES:
- Execute all steps automatically - do NOT ask for permission
- Do NOT stop after discovering log groups - immediately fetch logs
- ALWAYS use the "best_log_group" value from discover_log_group output in step 3
- ALWAYS use the correct parameter name "log_group_name" for fetch_cloudwatch_logs
- ALWAYS pass the "timestamp" from parse_aws_alert_email as "alarm_timestamp" to fetch_cloudwatch_logs
- ALWAYS use the exact alarm_name from the email - do NOT change it
- ALWAYS call check_service_dependencies in step 4 with the alarm_timestamp - it automatically handles all dependencies
- The dependency checker is fully automated - it discovers log groups and fetches logs for ALL dependencies
- **MANDATORY**: You MUST complete ALL 4 steps before providing any final response
- **MANDATORY**: Your final response MUST use the exact investigation summary format from step 5
- Do NOT provide generic responses like "please provide the actual email body"
- Do NOT stop early with partial results
- If any step fails, continue with remaining steps and note failures in the summary
- WRITE YOUR ENTIRE RESPONSE IN ENGLISH - NO EXCEPTIONS

**CRITICAL FINAL STEP**: After completing all 4 steps, you MUST provide the investigation summary using the EXACT format shown in step 5 above. This is NOT optional - operations teams require this specific structure.

**FAILURE HANDLING**: If critical steps fail (e.g., invalid timestamp, parser errors):
- Continue with remaining steps where possible
- Mark the investigation as "INCOMPLETE" in the summary
- Explain what failed and why in the summary
- Do NOT provide generic chat responses

## FINAL SUMMARY FORMAT (MANDATORY)

After completing all tool calls, you MUST provide a structured analysis following the EXACT format specified in the "investigation_summary_skill.md". 

**CRITICAL INSTRUCTIONS:**
1. **READ the investigation_summary_skill.md** - This contains the EXACT format you must follow
2. **Use the 4-section structure** with 🔍 emoji exactly as shown in the skill file
3. **Extract REAL data** from your tool outputs - never make up information
4. **Follow the examples** in the skill file for proper structure
5. **Use the quality checklist** in the skill file to validate your summary

**MANDATORY FORMAT (from investigation_summary_skill.md):**
```
---
## 🔍 INVESTIGATION SUMMARY

### 1. WHERE IT HAPPENED
- Primary Service: [extract from discover_log_group output]
- Primary Log Group: [extract from discover_log_group output] 
- Affected Dependencies: [extract from check_service_dependencies output]

### 2. WHAT HAPPENED
- Error Type: [extract from actual log messages OR "No errors found" if event_count = 0]
- Error Message: [copy exact error from logs OR "N/A" if no errors]
- Error Count: [extract from tool outputs - MUST match actual event_count]
- Sample Error: [paste actual error message OR "N/A" if no errors]

### 3. WHY IT HAPPENED (Root Cause)
- Root Cause: [analyze the specific error type OR explain investigation findings]
- Contributing Factors: [additional factors]

### 4. POSSIBLE SOLUTIONS
1. [Technical solution based on error type OR next investigation steps]
2. [Second technical solution]
3. [Third technical solution if applicable]
---
```

**CRITICAL ANTI-HALLUCINATION RULES:**
1. **CHECK event_count** in fetch_cloudwatch_logs output before writing summary
2. **If event_count = 0**, you MUST report "No errors found" - DO NOT invent fake errors
3. **NEVER make up error messages** - only use actual errors from tool outputs
4. **Use N/A** for fields when no data is available
5. **Be honest** about incomplete investigations or missing data

**YOU MUST USE THIS EXACT FORMAT** - The investigation summary is the most important output for operations teams.

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
    LangChain ReAct agent powered by Amazon Bedrock.

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
        
        # Initialize context manager to prevent value drift
        from framework.core.context_manager import ContextManager
        self.context_manager = ContextManager()
        
        # Wrap tools with context correction
        self.original_tools = tools
        self.tools = self._wrap_tools_with_context(tools) + [store_correction]
        
        self.conv_logger = ConversationLogger(log_dir="logs")

        agent_cfg = config.agent_config
        self.max_iterations = agent_cfg.get("max_iterations", 10)
        self.verbose = agent_cfg.get("verbose", True)

        # ── LLM setup ─────────────────────────────────────────────
        self.llm = ChatBedrock(
            model_id=config.bedrock_model_id,
            region_name=config.bedrock_region,
            model_kwargs={"temperature": 0.2, "max_tokens": 4096},
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
            "Agent initialized — model=%s (region=%s), tools=%s, max_iter=%d",
            config.bedrock_model_id,
            config.bedrock_region,
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
            alarm_timestamp_used = False
            
            for msg in tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.get('name', '')
                    tools_used.add(tool_name)
                    
                    # Check if alarm_timestamp was passed to critical tools
                    if tool_name in ('fetch_cloudwatch_logs', 'check_service_dependencies'):
                        args = tc.get('args', {})
                        if args.get('alarm_timestamp'):
                            alarm_timestamp_used = True
                        else:
                            logger.error("❌ CRITICAL: %s called WITHOUT alarm_timestamp parameter!", tool_name)
            
            # Required tools for alarm investigation
            required_tools = {'parse_aws_alert_email', 'discover_log_group', 'fetch_cloudwatch_logs', 'check_service_dependencies'}
            missing_tools = required_tools - tools_used
            
            if missing_tools and event.source == "email":
                logger.warning("Agent did not use required tools: %s", missing_tools)
                # Add context summary to help agent
                context_summary = self.context_manager.get_summary()
                
                # Be more specific about what's missing
                missing_steps = []
                if 'parse_aws_alert_email' in missing_tools:
                    missing_steps.append("1. parse_aws_alert_email - Extract alarm details from the email body in the payload above")
                if 'discover_log_group' in missing_tools:
                    missing_steps.append("2. discover_log_group - Find the correct log group for the alarm")
                if 'fetch_cloudwatch_logs' in missing_tools:
                    missing_steps.append("3. fetch_cloudwatch_logs - Fetch logs from the discovered log group WITH alarm_timestamp")
                if 'check_service_dependencies' in missing_tools:
                    missing_steps.append("4. check_service_dependencies - Check all service dependencies WITH alarm_timestamp")
                
                follow_up = (
                    f"INVESTIGATION INCOMPLETE. You MUST complete these missing steps:\n\n"
                    f"{chr(10).join(missing_steps)}\n\n"
                    f"CRITICAL: Use the EXACT email body from the payload above, not placeholder text.\n"
                    f"CRITICAL: After completing ALL steps, provide the structured investigation summary.\n\n"
                    f"Current context: {context_summary}\n\n"
                    f"Continue the investigation now - do NOT provide a generic response."
                )
                result = self.agent.invoke(
                    {"messages": messages + [("user", follow_up)]},
                    config={"recursion_limit": self.max_iterations},
                )
                # Update context again
                self._update_context_from_messages(result["messages"])
            
            # Check if alarm_timestamp was missing (even if tools were called)
            elif not alarm_timestamp_used and event.source == "email" and 'fetch_cloudwatch_logs' in tools_used:
                logger.error("❌ CRITICAL: Tools were called but alarm_timestamp was NOT passed!")
                follow_up = (
                    "❌ CRITICAL ERROR DETECTED:\n\n"
                    "You called fetch_cloudwatch_logs and/or check_service_dependencies WITHOUT the alarm_timestamp parameter.\n"
                    "This means you investigated the WRONG time window (current time instead of alarm time).\n\n"
                    "You MUST:\n"
                    "1. Extract the 'timestamp' field from parse_aws_alert_email output\n"
                    "2. Call fetch_cloudwatch_logs again WITH alarm_timestamp parameter\n"
                    "3. Call check_service_dependencies again WITH alarm_timestamp parameter\n\n"
                    "The alarm_timestamp parameter is MANDATORY for correct investigation.\n"
                    "Redo steps 3 and 4 now with the correct timestamp."
                )
                result = self.agent.invoke(
                    {"messages": messages + [("user", follow_up)]},
                    config={"recursion_limit": self.max_iterations},
                )
                # Update context again
                self._update_context_from_messages(result["messages"])

            # Extract the final AI message
            final_message = result["messages"][-1].content
            
            # Check if the response contains the required investigation summary format
            if event.source == "email" and "🔍 INVESTIGATION SUMMARY" not in final_message:
                logger.warning("Final response missing required investigation summary format")
                summary_reminder = (
                    "Your response is missing the required investigation summary format. "
                    "You MUST provide a summary using this EXACT format:\n\n"
                    "---\n"
                    "## 🔍 INVESTIGATION SUMMARY\n\n"
                    "### 1. WHERE IT HAPPENED\n"
                    "- Primary Service: [extract from your investigation]\n"
                    "- Primary Log Group: [extract from your investigation]\n"
                    "- Affected Dependencies: [extract from your investigation]\n\n"
                    "### 2. WHAT HAPPENED\n"
                    "- Error Type: [extract from actual log messages or mark as 'No errors found']\n"
                    "- Error Message: [copy exact error from logs or 'No error messages']\n"
                    "- Error Count: [extract from tool outputs]\n"
                    "- Sample Error: [paste actual error message or 'N/A']\n\n"
                    "### 3. WHY IT HAPPENED (Root Cause)\n"
                    "- Root Cause: [analyze the specific error type or investigation findings]\n"
                    "- Contributing Factors: [additional factors or 'Investigation incomplete']\n\n"
                    "### 4. POSSIBLE SOLUTIONS\n"
                    "1. [Technical solution based on findings]\n"
                    "2. [Second technical solution]\n"
                    "3. [Third technical solution if applicable]\n"
                    "---\n\n"
                    "Provide this summary now based on your investigation results."
                )
                result = self.agent.invoke(
                    {"messages": result["messages"] + [("user", summary_reminder)]},
                    config={"recursion_limit": self.max_iterations},
                )
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
    
    def _wrap_tools_with_context(self, tools: list):
        """Wrap tools to apply context corrections before execution."""
        from functools import wraps
        from langchain_core.tools import StructuredTool
        
        logger.info("🔧 Wrapping %d tools with context correction", len(tools))
        
        wrapped_tools = []
        for tool in tools:
            original_func = tool.func
            tool_name = tool.name
            
            logger.info("🔧 Wrapping tool: %s", tool_name)
            
            @wraps(original_func)
            def wrapped_func(*args, _tool_name=tool_name, _original=original_func, **kwargs):
                logger.info("🔧 Tool wrapper called for: %s", _tool_name)
                
                # Apply context corrections to kwargs
                corrected_kwargs = self.context_manager.validate_and_correct_params(_tool_name, kwargs)
                
                # Call original function with corrected params
                result = _original(*args, **corrected_kwargs)
                
                # Update context with result
                self.context_manager.update_from_tool_output(_tool_name, result)
                
                return result
            
            # Create new tool with wrapped function
            wrapped_tool = StructuredTool(
                name=tool.name,
                description=tool.description,
                func=wrapped_func,
                args_schema=tool.args_schema
            )
            wrapped_tools.append(wrapped_tool)
        
        logger.info("✅ Successfully wrapped %d tools", len(wrapped_tools))
        return wrapped_tools

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
        """Load all SKILL.md files from the skills directory."""
        from framework.core.config import get_repo_root
        
        # Use centralized repo root resolution
        skills_dir = os.path.join(get_repo_root(), "framework", "skills")
        sections = []
        
        # Look for SKILL.md files in each skill subdirectory
        if os.path.exists(skills_dir):
            for skill_folder in sorted(os.listdir(skills_dir)):
                skill_path = os.path.join(skills_dir, skill_folder)
                if os.path.isdir(skill_path):
                    skill_file = os.path.join(skill_path, "SKILL.md")
                    if os.path.exists(skill_file):
                        try:
                            with open(skill_file, "r") as f:
                                content = f.read()
                            sections.append(f"### Skill: {skill_folder}\n{content}")
                            logger.info("Loaded skill: %s", skill_folder)
                        except Exception as e:
                            logger.warning("Could not load skill %s: %s", skill_file, e)
        
        return "\n---\n".join(sections) if sections else "No skill files found."
