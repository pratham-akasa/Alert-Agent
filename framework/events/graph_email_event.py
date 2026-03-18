"""
Event Source: Microsoft Graph API Email Polling

Uses GraphEmailClient to poll a user's mailbox for new emails,
converts them into Event objects, and pushes them to the agent.
"""

import asyncio
import logging

from framework.events.base import Event, EventSource
from framework.core.graph_email_client import GraphEmailClient

logger = logging.getLogger(__name__)


class GraphEmailEventSource(EventSource):
    """
    Polls Microsoft Graph API for new unread emails and emits Event objects.

    Config keys (from config.yaml → email):
        tenantId, clientId, clientSecret, userId,
        poll_interval, subject_filter
    """

    def __init__(self, config: dict):
        super().__init__()
        self.subject_filter = config.get("subject_filter", "ALARM")
        self.poll_interval = config.get("poll_interval", 60)
        self._running = True
        self._processed_message_ids = set()
        self._client = GraphEmailClient(
            tenant_id=config.get("tenantId", ""),
            client_id=config.get("clientId", ""),
            client_secret=config.get("clientSecret", ""),
            user_id=config.get("userId", ""),
        )

    async def start(self) -> None:
        logger.info(
            "GraphEmailEventSource started — polling %s every %ds (filter: '%s')",
            self._client.user_id, self.poll_interval, self.subject_filter,
        )
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                logger.error("Graph API poll error: %s", e)
                self._client._access_token = None  # force token refresh on next poll
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        self._running = False

    async def _poll(self) -> None:
        messages = await self._client.list_messages(
            subject_filter=self.subject_filter,
            days_back=1,
            max_results=50,
            unread_only=True,
        )

        for message in messages:
            message_id = message["id"]

            if message_id in self._processed_message_ids:
                continue

            full_message = await self._client.read_message(message_id)

            subject = full_message.get("subject", "")
            sender = full_message.get("from", {}).get("emailAddress", {}).get("address", "")
            body = self._client.extract_body_text(full_message)

            event = Event(
                source="graph_email",
                event_type="aws_alarm",
                payload={
                    "messageId": message_id,
                    "subject": subject,
                    "from": sender,
                    "body": body,
                },
            )

            logger.info("Graph email event: %s from %s", subject, sender)
            self._emit(event)

            self._processed_message_ids.add(message_id)
            await self._client.mark_as_read(message_id)
