"""Quick verification script."""
import json
import os
import tempfile
from framework.tools.email_parser import parse_aws_alert_email
from framework.memory import Memory

# Test email parser
sample = json.dumps({
    "AlarmName": "TestAlarm",
    "NewStateValue": "ALARM",
    "OldStateValue": "OK",
    "NewStateReason": "Threshold crossed",
    "Region": "ap-south-1",
    "AWSAccountId": "123456789012",
    "StateChangeTime": "2026-03-04T12:00:00",
    "Trigger": {"MetricName": "CPUUtilization", "Namespace": "AWS/EC2", "Threshold": 80},
})

result = parse_aws_alert_email.invoke({"raw_email_body": sample})
parsed = json.loads(result)
print(f"  Alarm: {parsed['alarm_name']}")
print(f"  State: {parsed['new_state']}")
print(f"  Region: {parsed['region']}")
print("  Email parser OK")

# Test memory
mem = Memory(filepath=os.path.join(tempfile.gettempdir(), "test_memory.json"))
mem.store("test_key", "test_value")
assert mem.recall("test_key") == "test_value"
mem.add_event("Test event happened")
ctx = mem.get_context_summary()
assert "test_key" in ctx
print("  Memory OK")
mem.clear()

print("\nAll tests passed!")
