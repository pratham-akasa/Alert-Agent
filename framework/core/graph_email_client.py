"""
Microsoft Graph API Email Client

Provides utilities for listing and reading emails using Microsoft Graph API.
"""

import logging
from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class GraphEmailClient:
    """Client for Microsoft Graph API email operations."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, user_id: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self._access_token = None

    async def get_access_token(self) -> str:
        """Get OAuth2 access token using client credentials flow."""
        if self._access_token:
            return self._access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
            self._access_token = token_data["access_token"]
            logger.info("Successfully obtained Graph API access token")
            return self._access_token

    async def list_messages(
        self, 
        subject_filter: Optional[str] = None,
        days_back: int = 1,
        max_results: int = 50,
        unread_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List messages from user's mailbox.
        
        Args:
            subject_filter: Filter messages by subject containing this text
            days_back: How many days back to search
            max_results: Maximum number of messages to return
            unread_only: Only return unread messages
        """
        access_token = await self.get_access_token()
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_id}/messages"
        params = {
            "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
            "$orderby": "receivedDateTime desc",
            "$top": max_results
        }
        
        # Build filter conditions - use simpler filters that are more likely to work
        filters = []
        
        if unread_only:
            filters.append("isRead eq false")
        
        # Skip subject filtering on server side - do it client side instead
        # The contains() function seems to cause 400 errors
        
        # Try without date filter first to see if that's the issue
        if len(filters) > 0:
            params["$filter"] = " and ".join(filters)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                messages = data.get("value", [])
                
                # Filter by date in code if API filter fails
                if days_back > 0:
                    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
                    filtered_messages = []
                    for msg in messages:
                        received_str = msg.get("receivedDateTime", "")
                        if received_str:
                            try:
                                received_date = datetime.fromisoformat(received_str.replace('Z', '+00:00'))
                                if received_date >= cutoff_date:
                                    filtered_messages.append(msg)
                            except ValueError:
                                # If date parsing fails, include the message
                                filtered_messages.append(msg)
                    messages = filtered_messages
                
                logger.info(f"Found {len(messages)} messages matching criteria")
                return messages
                
            except Exception as e:
                # If filtering fails, try without filters
                logger.warning(f"Filtered query failed: {e}. Trying without filters...")
                simple_params = {
                    "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
                    "$orderby": "receivedDateTime desc",
                    "$top": max_results
                }
                
                response = await client.get(url, params=simple_params, headers=headers)
                response.raise_for_status()
                data = response.json()
                all_messages = data.get("value", [])
                
                # Apply filters in code
                filtered_messages = []
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back) if days_back > 0 else None
                
                for msg in all_messages:
                    # Check subject filter
                    if subject_filter:
                        subject = msg.get("subject", "").lower()
                        if subject_filter.lower() not in subject:
                            continue
                    
                    # Check read status
                    if unread_only and msg.get("isRead", False):
                        continue
                    
                    # Check date
                    if cutoff_date:
                        received_str = msg.get("receivedDateTime", "")
                        if received_str:
                            try:
                                received_date = datetime.fromisoformat(received_str.replace('Z', '+00:00'))
                                if received_date < cutoff_date:
                                    continue
                            except ValueError:
                                pass
                    
                    filtered_messages.append(msg)
                
                logger.info(f"Found {len(filtered_messages)} messages after client-side filtering")
                return filtered_messages

    async def read_message(self, message_id: str) -> Dict[str, Any]:
        """
        Read full message content by message ID.
        
        Args:
            message_id: The ID of the message to read
            
        Returns:
            Full message data including body content
        """
        access_token = await self.get_access_token()
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_id}/messages/{message_id}"
        params = {
            "$select": "id,subject,from,receivedDateTime,body,isRead,bodyPreview"
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            message_data = response.json()
            
            logger.info(f"Read message: {message_data.get('subject', 'No Subject')}")
            return message_data

    async def mark_as_read(self, message_id: str) -> None:
        """Mark message as read."""
        access_token = await self.get_access_token()
        
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_id}/messages/{message_id}"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        data = {"isRead": True}

        async with httpx.AsyncClient() as client:
            response = await client.patch(url, json=data, headers=headers)
            response.raise_for_status()
            logger.info(f"Marked message {message_id} as read")

    def extract_body_text(self, message_data: Dict[str, Any]) -> str:
        """Extract plain text from message data, stripping HTML if needed."""
        import re
        body_data = message_data.get("body", {})
        content_type = body_data.get("contentType", "").lower()
        content = body_data.get("content", "")

        if content_type == "html" or "<html" in content.lower():
            text = re.sub(r'<[^>]+>', ' ', content)
            text = (text
                    .replace('&nbsp;', ' ')
                    .replace('&amp;', '&')
                    .replace('&lt;', '<')
                    .replace('&gt;', '>')
                    .replace('&quot;', '"')
                    .replace('&#39;', "'"))
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n\s*\n+', '\n\n', text)
            return text.strip()
        return content.strip()