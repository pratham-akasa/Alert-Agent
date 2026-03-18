"""
Graph API Backfill script — pulls alarm emails from the last N days using Microsoft Graph API
and processes them through the agent.

Usage:
    python backfill_graph_emails.py               # Last 3 days (default)
    python backfill_graph_emails.py --days 7      # Last 7 days
    python backfill_graph_emails.py --dry-run     # Just list emails, don't process
"""

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from framework.core.config import Config
from framework.core.memory import Memory
from framework.core.agent import Agent
from framework.events.base import Event
from framework.tools.email_parser import parse_aws_alert_email
from framework.tools.cloudwatch_fetcher import fetch_cloudwatch_logs
from framework.tools.log_group_discovery import search_log_groups, discover_log_group
from framework.tools.dependency_checker import check_service_dependencies
from framework.core.graph_email_client import GraphEmailClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("graph_backfill")

ALL_TOOLS = [
    parse_aws_alert_email,
    fetch_cloudwatch_logs,
    discover_log_group,
    search_log_groups,
    check_service_dependencies,
]


async def fetch_emails(config: Config, days_back: int = 3) -> list[dict]:
    """Fetch all alarm emails from the last N days via Microsoft Graph API."""
    email_cfg = config.email_config
    
    client = GraphEmailClient(
        tenant_id=email_cfg.get("tenantId"),
        client_id=email_cfg.get("clientId"),
        client_secret=email_cfg.get("clientSecret"),
        user_id=email_cfg.get("userId")
    )

    subject_filter = email_cfg.get("subject_filter", "ALARM")
    logger.info("Fetching emails from Graph API for user: %s", email_cfg.get("userId"))
    
    # Get list of messages
    messages = await client.list_messages(
        subject_filter=subject_filter,
        days_back=days_back,
        max_results=100,
        unread_only=False  # Get both read and unread for backfill
    )

    if not messages:
        logger.info("No emails found.")
        return []

    logger.info("Found %d emails, reading full content...", len(messages))

    emails = []
    for message in messages:
        try:
            # Get full message content
            full_message = await client.read_message(message["id"])
            
            subject = full_message.get("subject", "")
            sender = full_message.get("from", {}).get("emailAddress", {}).get("address", "")
            received_date = full_message.get("receivedDateTime", "")
            body = client.extract_body_text(full_message)

            emails.append({
                "messageId": message["id"],
                "subject": subject,
                "from": sender,
                "date": received_date,
                "body": body,
            })
            
        except Exception as e:
            logger.error("Error reading message %s: %s", message["id"], e)
            continue

    return emails


async def main():
    parser = argparse.ArgumentParser(description="Backfill historical alarm emails using Graph API")
    parser.add_argument("--days", type=int, default=3, help="How many days back to fetch (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="List emails only, don't process through agent")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = Config(config_path=args.config)
    emails = await fetch_emails(config, days_back=args.days)

    if not emails:
        logger.info("Nothing to process.")
        return

    if args.dry_run:
        print(f"\nFound {len(emails)} emails (dry run — not processing):\n")
        for i, e in enumerate(emails, 1):
            print(f"  {i:3}. [{e['date']}] {e['subject']}")
            print(f"       From: {e['from']}")
            print(f"       ID: {e['messageId']}")
            print()
        return

    # Process each email through the agent
    memory = Memory(filepath=config.agent_config.get("memory_file", "memory.json"))
    agent = Agent(config=config, tools=ALL_TOOLS, memory=memory)

    logger.info("Processing %d emails through agent...", len(emails))
    for i, e in enumerate(emails, 1):
        logger.info("[%d/%d] %s", i, len(emails), e["subject"])
        event = Event(
            source="graph_email",
            event_type="aws_alarm",
            payload={
                "messageId": e["messageId"],
                "subject": e["subject"],
                "from": e["from"],
                "body": e["body"],
            },
        )
        result = agent.process_event(event)
        logger.info("Done: %s...", result[:100])

    logger.info("Graph API backfill complete. Processed %d emails.", len(emails))


if __name__ == "__main__":
    asyncio.run(main())