"""
Test script for Microsoft Graph API email integration.

Usage:
    python test_graph_api.py --list      # List recent emails
    python test_graph_api.py --read <message_id>  # Read specific email
"""

import argparse
import asyncio
import logging
from framework.core.config import Config
from framework.core.graph_email_client import GraphEmailClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_graph")


async def test_list_emails(config: Config):
    """Test listing emails."""
    email_cfg = config.email_config
    
    client = GraphEmailClient(
        tenant_id=email_cfg.get("tenantId"),
        client_id=email_cfg.get("clientId"),
        client_secret=email_cfg.get("clientSecret"),
        user_id=email_cfg.get("userId")
    )
    
    print("Testing Graph API connection...")
    print(f"User: {email_cfg.get('userId')}")
    print(f"Tenant: {email_cfg.get('tenantId')}")
    print()
    
    try:
        # Test authentication
        token = await client.get_access_token()
        print("✓ Successfully obtained access token")
        
        # First try: Get any recent emails without filters
        print("Trying to get recent emails without filters...")
        messages = await client.list_messages(
            subject_filter=None,  # No subject filter
            days_back=0,          # No date filter
            max_results=5,
            unread_only=False     # Get both read and unread
        )
        
        print(f"✓ Found {len(messages)} total emails")
        
        if messages:
            print("\nRecent emails (any subject):")
            print("-" * 80)
            for i, msg in enumerate(messages, 1):
                subject = msg.get("subject", "No Subject")
                sender = msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
                received = msg.get("receivedDateTime", "")
                message_id = msg.get("id", "")
                is_read = msg.get("isRead", False)
                
                print(f"{i}. {subject}")
                print(f"   From: {sender}")
                print(f"   Received: {received}")
                print(f"   Read: {is_read}")
                print(f"   ID: {message_id}")
                print()
        
        # Second try: Look for ALARM emails
        print("Now trying to find ALARM emails...")
        alarm_messages = await client.list_messages(
            subject_filter="ALARM",
            days_back=7,
            max_results=10,
            unread_only=False
        )
        
        print(f"✓ Found {len(alarm_messages)} ALARM emails")
        
        if alarm_messages:
            print("\nALARM emails:")
            print("-" * 80)
            for i, msg in enumerate(alarm_messages, 1):
                subject = msg.get("subject", "No Subject")
                sender = msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
                received = msg.get("receivedDateTime", "")
                message_id = msg.get("id", "")
                is_read = msg.get("isRead", False)
                
                print(f"{i}. {subject}")
                print(f"   From: {sender}")
                print(f"   Received: {received}")
                print(f"   Read: {is_read}")
                print(f"   ID: {message_id}")
                print()
        else:
            print("No emails found with 'ALARM' in subject in the last 7 days.")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        logger.exception("Full error details:")


async def test_read_email(config: Config, message_id: str):
    """Test reading a specific email."""
    email_cfg = config.email_config
    
    client = GraphEmailClient(
        tenant_id=email_cfg.get("tenantId"),
        client_id=email_cfg.get("clientId"),
        client_secret=email_cfg.get("clientSecret"),
        user_id=email_cfg.get("userId")
    )
    
    try:
        print(f"Reading email: {message_id}")
        print()
        
        message_data = await client.read_message(message_id)
        
        subject = message_data.get("subject", "No Subject")
        sender = message_data.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
        received = message_data.get("receivedDateTime", "")
        body = client.extract_body_text(message_data)
        
        print("Email Details:")
        print("=" * 60)
        print(f"Subject: {subject}")
        print(f"From: {sender}")
        print(f"Received: {received}")
        print("=" * 60)
        print()
        print("Body:")
        print(body)
        
    except Exception as e:
        print(f"✗ Error reading email: {e}")
        logger.exception("Full error details:")


async def main():
    parser = argparse.ArgumentParser(description="Test Microsoft Graph API email integration")
    parser.add_argument("--list", action="store_true", help="List recent emails")
    parser.add_argument("--read", type=str, help="Read specific email by message ID")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = Config(config_path=args.config)
    
    if args.list:
        await test_list_emails(config)
    elif args.read:
        await test_read_email(config, args.read)
    else:
        print("Use --list to list emails or --read <message_id> to read a specific email")


if __name__ == "__main__":
    asyncio.run(main())