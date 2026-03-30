"""
Agent Tools for Microsoft Graph API Email Operations

Provides tools for the agent to list and read emails using Graph API.
"""

import asyncio
import logging
from langchain_core.tools import tool

from framework.core.graph_email_client import GraphEmailClient

logger = logging.getLogger(__name__)


@tool
def list_graph_emails(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    user_id: str,
    subject_filter: str = "ALARM",
    days_back: int = 1,
    max_results: int = 20
) -> str:
    """
    List emails from Microsoft Graph API.

    Args:
        tenant_id: Azure AD tenant ID
        client_id: Application client ID
        client_secret: Application client secret
        user_id: Email address of the user
        subject_filter: Filter emails by subject containing this text
        days_back: How many days back to search (default: 1)
        max_results: Maximum number of emails to return (default: 20)

    Returns:
        Formatted string with email list including message IDs
    """
    async def _list():
        try:
            client = GraphEmailClient(tenant_id, client_id, client_secret, user_id)
            messages = await client.list_messages(
                subject_filter=subject_filter,
                days_back=days_back,
                max_results=max_results,
                unread_only=True
            )

            if not messages:
                return f"No unread emails found with subject containing '{subject_filter}' in the last {days_back} days."

            result = f"Found {len(messages)} unread emails matching '{subject_filter}':\n\n"
            for i, msg in enumerate(messages, 1):
                subject = msg.get("subject", "No Subject")
                sender = msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
                received = msg.get("receivedDateTime", "")
                message_id = msg.get("id", "")
                preview = msg.get("bodyPreview", "")
                if preview and len(preview) > 100:
                    preview = preview[:100] + "..."

                result += f"{i}. Message ID: {message_id}\n"
                result += f"   Subject: {subject}\n"
                result += f"   From: {sender}\n"
                result += f"   Received: {received}\n"
                if preview:
                    result += f"   Preview: {preview}\n"
                result += "\n"

            return result

        except Exception as e:
            logger.error(f"Error listing emails: {e}")
            return f"Error listing emails: {str(e)}"

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _list())
                return future.result()
        return loop.run_until_complete(_list())
    except RuntimeError:
        return asyncio.run(_list())


@tool
def read_graph_email(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    user_id: str,
    message_id: str,
    mark_as_read: bool = True
) -> str:
    """
    Read a specific email using Microsoft Graph API.

    Args:
        tenant_id: Azure AD tenant ID
        client_id: Application client ID
        client_secret: Application client secret
        user_id: Email address of the user
        message_id: The ID of the message to read (from list_graph_emails)
        mark_as_read: Whether to mark the message as read after reading

    Returns:
        Full email content as formatted string
    """
    async def _read():
        try:
            client = GraphEmailClient(tenant_id, client_id, client_secret, user_id)
            message_data = await client.read_message(message_id)

            subject = message_data.get("subject", "No Subject")
            sender = message_data.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
            received = message_data.get("receivedDateTime", "")
            body = client.extract_body_text(message_data)

            result = "Email Details:\n"
            result += "=" * 50 + "\n"
            result += f"Message ID: {message_id}\n"
            result += f"Subject: {subject}\n"
            result += f"From: {sender}\n"
            result += f"Received: {received}\n"
            result += "=" * 50 + "\n\n"
            result += f"Body:\n{body}"

            if mark_as_read:
                await client.mark_as_read(message_id)
                result += "\n\n[Message marked as read]"

            return result

        except Exception as e:
            logger.error(f"Error reading email {message_id}: {e}")
            return f"Error reading email: {str(e)}"

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _read())
                return future.result()
        return loop.run_until_complete(_read())
    except RuntimeError:
        return asyncio.run(_read())