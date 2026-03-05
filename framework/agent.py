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

SYSTEM_PROMPT = """You are an autonomous AWS alert handling agent.

Your job:
1. Analyze incoming events (email alerts, manual inputs).
2. Use the available tools (skills) to parse, investigate, and gather context.
3. Provide a clear, actionable summary of what happened and what should be done.
4. Notify the team via MS Teams after completing your investigation.
5. If a user corrects your analysis, store the correction for future reference.

Guidelines:
- Always start by parsing the alert to understand what alarm fired and why.
- After parsing, look up the alarm in the service registry to find log groups, owner team, and dependencies.
- If you have a log group name, fetch CloudWatch logs to get more context.
- Check the corrections below — if a user has previously corrected your analysis for this alarm, apply that correction.
- After completing your investigation, send the summary to MS Teams.
- Be concise but thorough in your final summary.
- If you cannot determine the log group, state that clearly and suggest next steps.
- If a user tells you something was wrong or gives you new information, use the store_correction tool to remember it.

## Available Skills
{skills_context}

## Agent Memory
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

        # Build the user message from the event
        user_message = self._format_event(event)

        # Run the agent
        start_time = time.time()
        try:
            result = self.agent.invoke(
                {"messages": [("user", user_message)]},
                config={"recursion_limit": self.max_iterations},
            )

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
                "\nPlease parse this alert email and investigate the alarm. "
                "If you can determine the relevant log group, fetch recent CloudWatch logs."
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
