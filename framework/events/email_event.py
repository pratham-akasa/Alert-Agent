"""
Event Source: IMAP Email Polling

Polls an IMAP mailbox for unread emails matching a subject filter,
converts them into Event objects, and pushes them to the agent.
"""

import asyncio
import email
import imaplib
import logging
from email.header import decode_header
from typing import Optional

from framework.events.base import Event, EventSource

logger = logging.getLogger(__name__)


class EmailEventSource(EventSource):
    """
    Polls an IMAP mailbox for new unread emails and emits Event objects.

    Config keys (from config.yaml → email):
        imap_server, imap_port, username, password,
        folder, poll_interval, subject_filter
    """

    def __init__(self, config: dict):
        super().__init__()
        self.server = config.get("imap_server", "imap.gmail.com")
        self.port = config.get("imap_port", 993)
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.folder = config.get("folder", "INBOX")
        self.poll_interval = config.get("poll_interval", 60)
        self.subject_filter = config.get("subject_filter", "ALARM")
        self._running = True

    async def start(self) -> None:
        """Poll the mailbox in a loop."""
        logger.info(
            "EmailEventSource started — polling %s@%s every %ds (filter: '%s')",
            self.username, self.server, self.poll_interval, self.subject_filter,
        )
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                logger.error("Email poll error: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        self._running = False

    async def _poll(self) -> None:
        """Connect to IMAP, search for unread matching emails, emit events."""
        loop = asyncio.get_event_loop()
        # Run blocking IMAP calls in a thread pool
        await loop.run_in_executor(None, self._poll_sync)

    def _poll_sync(self) -> None:
        """Synchronous IMAP polling logic."""
        mail: Optional[imaplib.IMAP4_SSL] = None
        try:
            mail = imaplib.IMAP4_SSL(self.server, self.port)
            mail.login(self.username, self.password)
            mail.select(self.folder)

            # Search for unseen emails matching subject
            search_criteria = f'(UNSEEN SUBJECT "{self.subject_filter}")'
            status, msg_ids = mail.search(None, search_criteria)

            if status != "OK" or not msg_ids[0]:
                return

            for msg_id in msg_ids[0].split():
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                subject = self._decode_header(msg.get("Subject", ""))
                sender = self._decode_header(msg.get("From", ""))
                body = self._get_body(msg)

                event = Event(
                    source="email",
                    event_type="aws_alarm",
                    payload={
                        "subject": subject,
                        "from": sender,
                        "body": body,
                    },
                )
                logger.info("Email event: %s from %s", subject, sender)
                self._emit(event)

                # Mark as seen so we don't reprocess
                mail.store(msg_id, "+FLAGS", "\\Seen")

        except imaplib.IMAP4.error as e:
            logger.error("IMAP error: %s", e)
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

    @staticmethod
    def _decode_header(header_value: str) -> str:
        """Decode MIME-encoded email header."""
        parts = decode_header(header_value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    @staticmethod
    def _get_body(msg: email.message.Message) -> str:
        """Extract the text/plain body from an email message."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")
        return ""
