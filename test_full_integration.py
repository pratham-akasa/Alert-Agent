"""
Comprehensive test of the Graph API integration.
Tests all components: authentication, listing, reading, and agent tools.
"""

import asyncio
import logging
from framework.core.config import Config
from framework.core.graph_email_client import GraphEmailClient
from framework.tools.graph_email_tools import list_graph_emails, read_graph_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integration_test")


async def test_integration():
    """Test the full Graph API integration."""
    print("=" * 60)
    print("GRAPH API INTEGRATION TEST")
    print("=" * 60)
    
    config = Config(config_path="config.yaml")
    email_cfg = config.email_config
    
    print(f"User: {email_cfg.get('userId')}")
    print(f"Tenant: {email_cfg.get('tenantId')}")
    print()
    
    # Test 1: Direct client access
    print("1. Testing direct GraphEmailClient...")
    try:
        client = GraphEmailClient(
            tenant_id=email_cfg.get("tenantId"),
            client_id=email_cfg.get("clientId"),
            client_secret=email_cfg.get("clientSecret"),
            user_id=email_cfg.get("userId")
        )
        
        # Get access token
        token = await client.get_access_token()
        print("   ✓ Authentication successful")
        
        # List recent emails
        messages = await client.list_messages(
            subject_filter=None,
            days_back=0,
            max_results=3,
            unread_only=False
        )
        print(f"   ✓ Found {len(messages)} recent emails")
        
        if messages:
            latest_message = messages[0]
            message_id = latest_message["id"]
            subject = latest_message.get("subject", "No Subject")
            
            # Read the latest email
            full_message = await client.read_message(message_id)
            print(f"   ✓ Successfully read email: '{subject}'")
            
            # Test body extraction
            body = client.extract_body_text(full_message)
            print(f"   ✓ Extracted body text ({len(body)} characters)")
            
    except Exception as e:
        print(f"   ✗ Direct client test failed: {e}")
        return False
    
    # Test 2: Agent tools (via .invoke() since they are LangChain StructuredTools)
    print("\n2. Testing agent tools...")
    try:
        # Test list tool
        result = list_graph_emails.invoke({
            "tenant_id": email_cfg.get("tenantId"),
            "client_id": email_cfg.get("clientId"),
            "client_secret": email_cfg.get("clientSecret"),
            "user_id": email_cfg.get("userId"),
            "subject_filter": "ALARM",
            "days_back": 7,
            "max_results": 3
        })
        print("   ✓ list_graph_emails tool works")
        print(f"   Result preview: {result[:100]}...")

        # If we have messages, test read tool
        if messages:
            message_id = messages[0]["id"]
            read_result = read_graph_email.invoke({
                "tenant_id": email_cfg.get("tenantId"),
                "client_id": email_cfg.get("clientId"),
                "client_secret": email_cfg.get("clientSecret"),
                "user_id": email_cfg.get("userId"),
                "message_id": message_id,
                "mark_as_read": False
            })
            print("   ✓ read_graph_email tool works")
            print(f"   Result preview: {read_result[:100]}...")
        
    except Exception as e:
        print(f"   ✗ Agent tools test failed: {e}")
        return False
    
    # Test 3: ALARM email filtering
    print("\n3. Testing ALARM email filtering...")
    try:
        alarm_messages = await client.list_messages(
            subject_filter="ALARM",
            days_back=30,
            max_results=10,
            unread_only=False
        )
        print(f"   ✓ Found {len(alarm_messages)} ALARM emails in last 30 days")
        
        if alarm_messages:
            for i, msg in enumerate(alarm_messages[:3], 1):
                subject = msg.get("subject", "No Subject")
                received = msg.get("receivedDateTime", "")
                print(f"   {i}. {subject} ({received})")
        else:
            print("   ℹ No ALARM emails found - this is normal if none exist")
            
    except Exception as e:
        print(f"   ✗ ALARM filtering test failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - Graph API integration is working!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Send a test email with 'ALARM' in subject to test the full flow")
    print("2. Run: python main.py --test")
    print("3. Run: python main.py (for production mode)")
    
    return True


if __name__ == "__main__":
    asyncio.run(test_integration())