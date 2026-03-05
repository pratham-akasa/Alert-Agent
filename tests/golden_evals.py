"""
Golden Evaluation Cases — known alerts with expected outcomes.

Each case defines an input email, the alarm name the parser should extract,
the log group the service registry should resolve, and keywords the agent's
final summary should contain.

Add new cases from real past alerts to expand test coverage.
"""

# ── Golden Cases ──────────────────────────────────────────────────────────

GOLDEN_CASES = [
    {
        "name": "qp-booking-service-common-error",
        "description": "Standard booking service error alarm from CloudWatch",
        "input_email": {
            "subject": "ALARM: qp-booking-service-common-error in Asia Pacific (Mumbai)",
            "from": "no-reply@sns.amazonaws.com",
            "body": (
                'You are receiving this email because your Amazon CloudWatch Alarm '
                '"qp-booking-service-common-error" in the Asia Pacific (Mumbai) region '
                'has entered the ALARM state.\n\n'
                '- Name: qp-booking-service-common-error\n'
                '- Description: Common error alarm for booking service\n'
                '- State Change: OK -> ALARM\n'
                '- Reason for State Change: Threshold Crossed: 1 datapoint [5.0 '
                '(20/02/26 04:08:00)] was greater than or equal to the threshold (1.0).\n'
                '- Timestamp: Wednesday 04 March, 2026 04:08:18 UTC\n'
                '- AWS Account: 471112573018\n'
                '- Alarm Arn: arn:aws:cloudwatch:ap-south-1:471112573018:alarm:'
                'qp-booking-service-common-error\n'
                '- MetricName: ErrorCount\n\n'
                'View this alarm in the AWS Management Console:\n'
                'https://console.aws.amazon.com/cloudwatch/home?region=ap-south-1'
                '#alarm:alarmFilter=ANY;name=qp-booking-service-common-error\n'
            ),
        },
        "expected_alarm_name": "qp-booking-service-common-error",
        "expected_state": "ALARM",
        "expected_region": "ap-south-1",
        "expected_log_group": "/copilot/qp-prod-qp-booking-webservice",
        "expected_owner_team": "booking-platform",
        "expected_summary_keywords": ["booking", "error", "ALARM"],
    },
    {
        "name": "booking-service-json-payload",
        "description": "Booking service alarm with embedded JSON (SNS format)",
        "input_email": {
            "subject": "ALARM: qp-booking-service-common-error",
            "from": "no-reply@sns.amazonaws.com",
            "body": (
                '{"AlarmName": "qp-booking-service-common-error", '
                '"NewStateValue": "ALARM", '
                '"OldStateValue": "OK", '
                '"NewStateReason": "Threshold Crossed: 1 datapoint was >= threshold", '
                '"Region": "Asia Pacific (Mumbai)", '
                '"AWSAccountId": "471112573018", '
                '"StateChangeTime": "2026-03-04T04:08:18.000+0000", '
                '"Trigger": {"MetricName": "ErrorCount", "Namespace": "AWS/Logs", '
                '"Threshold": 1.0, "ComparisonOperator": "GreaterThanOrEqualToThreshold"}}'
            ),
        },
        "expected_alarm_name": "qp-booking-service-common-error",
        "expected_state": "ALARM",
        "expected_log_group": "/copilot/qp-prod-qp-booking-webservice",
        "expected_owner_team": "booking-platform",
        "expected_summary_keywords": ["booking", "error", "ALARM"],
    },
]

# ── Template for adding new cases ─────────────────────────────────────────
#
# {
#     "name": "descriptive-test-name",
#     "description": "What this test covers",
#     "input_email": {
#         "subject": "ALARM: ...",
#         "from": "no-reply@sns.amazonaws.com",
#         "body": "...",
#     },
#     "expected_alarm_name": "alarm-name",
#     "expected_state": "ALARM",
#     "expected_region": "ap-south-1",
#     "expected_log_group": "/log/group/path",
#     "expected_owner_team": "team-name",
#     "expected_summary_keywords": ["keyword1", "keyword2"],
# },
