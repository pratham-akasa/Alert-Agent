"""
AWS Alert Bot — Main Entry Point

Wires the agent, tools, and event sources together and runs the async event loop.

Usage:
    python main.py              # Run with email polling
    python main.py --test       # Smoke test with a fake AWS alarm
    python main.py --interactive  # Interactive chat mode
"""

import argparse
import asyncio
import json
import logging
import sys

from framework.core.config import Config
from framework.core.memory import Memory
from framework.core.agent import Agent
from framework.events.base import Event
from framework.tools.email_parser import parse_aws_alert_email
from framework.tools.cloudwatch_fetcher import fetch_cloudwatch_logs
from framework.tools.graph_email_tools import list_graph_emails, read_graph_email
from framework.tools.log_group_discovery import search_log_groups, discover_log_group
from framework.tools.dependency_checker import check_service_dependencies


# ── Logging ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── Tool registry ─────────────────────────────────────────────────────

ALL_TOOLS = [
    parse_aws_alert_email,
    fetch_cloudwatch_logs,
    discover_log_group,
    search_log_groups,
    check_service_dependencies,
    list_graph_emails,
    read_graph_email,
]


# ── Test data ──────────────────────────────────────────────────────────

SAMPLE_SUBJECT = "ALARM: qp-booking-service-common-error in Asia Pacific (Mumbai)"
SAMPLE_FROM = "no-reply@sns.amazonaws.com"
SAMPLE_BODY = """You are receiving this email because your Amazon CloudWatch Alarm "qp-booking-service-common-error" in the Asia Pacific (Mumbai) region has entered the ALARM state.

- Name: qp-booking-service-common-error
- Description: Common error alarm for booking service
- State Change: OK -> ALARM
- Reason for State Change: Threshold Crossed: 1 datapoint [5.0 (17/03/26 14:08:00)] was greater than or equal to the threshold (1.0).
- Timestamp: Tuesday 17 March, 2026 14:08:18 UTC
- AWS Account: 471112573018
- Alarm Arn: arn:aws:cloudwatch:ap-south-1:471112573018:alarm:qp-booking-service-common-error
- MetricName: ErrorCount

View this alarm in the AWS Management Console:
https://console.aws.amazon.com/cloudwatch/home?region=ap-south-1#alarm:alarmFilter=ANY;name=qp-booking-service-common-error
"""

def create_agent(config: Config) -> Agent:
    """Create and configure the agent."""
    memory_file = config.agent_config.get("memory_file", "memory.json")
    memory = Memory(filepath=memory_file)
    agent = Agent(config=config, tools=ALL_TOOLS, memory=memory)
    return agent


async def run_test(config: Config) -> None:
    """Smoke test: send a sample AWS alarm through the agent."""
    logger.info("=" * 60)
    logger.info("SMOKE TEST — Sample AWS CloudWatch alarm")
    logger.info("=" * 60)

    agent = create_agent(config)

    event = Event(
        source="email",
        event_type="aws_alarm",
        payload={
            "subject": SAMPLE_SUBJECT,
            "from": SAMPLE_FROM,
            "body": SAMPLE_BODY,
        },
    )

    result = agent.process_event(event)
    print("\n" + "=" * 60)
    print("AGENT RESPONSE:")
    print("=" * 60)
    print(result)


async def run_interactive(config: Config) -> None:
    """Interactive chat mode — type messages and see agent responses."""
    logger.info("Interactive mode — type 'quit' to exit")
    agent = create_agent(config)

    while True:
        try:
            user_input = input("\n🤖 You: ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break
            if not user_input:
                continue

            result = agent.process_text(user_input)
            print(f"\n🤖 Agent: {result}")

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


async def run_daemon(config: Config) -> None:
    """Production mode: run event sources + process events via agent."""
    agent = create_agent(config)

    event_sources = []

    # ── Email event source ─────────────────────────────────────────
    email_cfg = config.email_config
    if email_cfg.get("userId"):  # Changed from "username" to "userId" for Graph API
        from framework.events.graph_email_event import GraphEmailEventSource
        email_source = GraphEmailEventSource(email_cfg)
        email_source.on_event(lambda evt: agent.process_event(evt))
        event_sources.append(email_source)
        logger.info("Graph API email event source enabled")
    else:
        logger.warning("Email event source skipped — no userId configured")

    if not event_sources:
        logger.error("No event sources configured! Set up email credentials in config.yaml.")
        sys.exit(1)

    # Start all event sources concurrently
    logger.info("Starting %d event source(s)...", len(event_sources))
    tasks = [asyncio.create_task(source.start()) for source in event_sources]

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        for source in event_sources:
            await source.stop()


def main():
    parser = argparse.ArgumentParser(description="AWS Alert Bot — Autonomous Agent")
    parser.add_argument("--test", action="store_true", help="Run smoke test with fake alarm")
    parser.add_argument("--interactive", action="store_true", help="Interactive chat mode")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = Config(config_path=args.config)

    logger.info("AWS Alert Bot starting...")
    logger.info("Model: %s @ %s", config.bedrock_model_id, config.bedrock_region)
    logger.info("Tools: %s", [t.name for t in ALL_TOOLS])

    if args.test:
        asyncio.run(run_test(config))
    elif args.interactive:
        asyncio.run(run_interactive(config))
    else:
        asyncio.run(run_daemon(config))


if __name__ == "__main__":
    main()
