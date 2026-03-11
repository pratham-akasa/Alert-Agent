"""
Conversation Logger — saves each agent interaction to a timestamped log file.

Each run produces a markdown file in the logs/ directory containing:
  - Timestamp and event details
  - Full agent prompt (user message)
  - All tool calls and their results
  - Final agent response
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any


class ConversationLogger:
    """Writes structured logs for every agent run."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    def save(
        self,
        event_source: str,
        event_type: str,
        user_message: str,
        messages: list[Any],
        final_response: str,
        duration_seconds: float = 0.0,
    ) -> str:
        """
        Save a full conversation to a log file.

        Args:
            event_source: e.g. 'email', 'manual'
            event_type: e.g. 'aws_alarm', 'user_input'
            user_message: the formatted prompt sent to the agent
            messages: the full list of LangGraph messages (includes tool calls/results)
            final_response: the agent's final text response
            duration_seconds: how long the agent took

        Returns:
            The path to the saved log file.
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

        # Sanitize event type for filename
        safe_type = re.sub(r"[^\w\-]", "_", event_type)
        filename = f"{timestamp}_{safe_type}.md"
        filepath = os.path.join(self.log_dir, filename)

        lines = [
            f"# Agent Run — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            f"**Source**: {event_source}",
            f"**Type**: {event_type}",
            f"**Duration**: {duration_seconds:.1f}s",
            "",
            "---",
            "",
            "## Input Event",
            "",
            "```",
            user_message,
            "```",
            "",
        ]

        # Extract tool calls and results from the message chain
        tool_calls = self._extract_tool_interactions(messages)
        if tool_calls:
            lines.append("## Tool Calls")
            lines.append("")
            for i, tc in enumerate(tool_calls, 1):
                lines.append(f"### {i}. `{tc['tool']}`")
                lines.append("")
                if tc.get("input"):
                    lines.append("**Input:**")
                    lines.append("```json")
                    lines.append(json.dumps(tc["input"], indent=2, default=str))
                    lines.append("```")
                    lines.append("")
                if tc.get("output"):
                    lines.append("**Output:**")
                    lines.append("```")
                    output_str = str(tc["output"])
                    # Truncate very long outputs
                    if len(output_str) > 2000:
                        output_str = output_str[:2000] + "\n... (truncated)"
                    lines.append(output_str)
                    lines.append("```")
                    lines.append("")

        lines.extend([
            "---",
            "",
            "## Final Response",
            "",
            final_response,
            "",
        ])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return filepath

    @staticmethod
    def _extract_tool_interactions(messages: list[Any]) -> list[dict]:
        """
        Walk the LangGraph message list and pull out tool call / result pairs.
        """
        tool_calls = []

        for msg in messages:
            # AIMessage with tool_calls
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "tool": tc.get("name", "unknown"),
                        "input": tc.get("args", {}),
                        "output": None,
                    })

            # ToolMessage (result of a tool call)
            if hasattr(msg, "type") and msg.type == "tool":
                tool_name = getattr(msg, "name", "unknown")
                content = getattr(msg, "content", "")
                # Try to match it back to the last pending tool call
                for tc in reversed(tool_calls):
                    if tc["tool"] == tool_name and tc["output"] is None:
                        tc["output"] = content
                        break
                else:
                    # Orphan tool result
                    tool_calls.append({
                        "tool": tool_name,
                        "input": None,
                        "output": content,
                    })

        return tool_calls
