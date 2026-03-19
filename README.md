# AWS Alert Bot

Autonomous Python agent for investigating AWS CloudWatch alarms from email alerts.

Reads alarm emails via Microsoft Graph API, parses alarm details, discovers relevant CloudWatch log groups, fetches logs around the alarm timestamp, checks known dependencies, posts an investigation summary to Microsoft Teams, and writes full investigation runs to local markdown logs.

## What This Does

- Polls a Microsoft 365 mailbox using Microsoft Graph API (OAuth2 client credentials)
- Runs a LangGraph ReAct agent backed by Amazon Bedrock (`amazon.nova-lite`)
- Auto-infers alert severity from investigation content (Critical / High / Medium / Low)
- Posts structured investigation summaries to a Microsoft Teams channel via Adaptive Cards
- Supports 3 modes:
  - daemon email polling mode (`python main.py`)
  - smoke test mode (`python main.py --test`)
  - interactive prompt mode (`python main.py --interactive`)
- Stores memory and corrections in `memory.json`
- Writes per-run investigation logs into `logs/`

## Active Tools

| Tool | Purpose |
|------|---------|
| `parse_aws_alert_email` | Extracts alarm name, timestamp, region, metric from email body |
| `discover_log_group` | Finds the best matching log group via AWS Resource Explorer |
| `search_log_groups` | Manual log group search |
| `fetch_cloudwatch_logs` | Fetches logs from CloudWatch around alarm timestamp |
| `check_service_dependencies` | Fetches logs for all dependent services |
| `list_graph_emails` | Lists unread alarm emails via Graph API |
| `read_graph_email` | Reads full email content by message ID |
| `notify_teams` | Posts investigation summary to Teams via Adaptive Card |
| `store_correction` | Stores per-alarm corrections in memory for future runs |

## Project Structure

```text
.
├── main.py                          # Entry point
├── backfill_graph_emails.py         # Backfill historical emails
├── test_graph_api.py                # Test Graph API connection
├── test_full_integration.py         # Full integration test
├── config.yaml                      # Configuration
├── services.yaml                    # Service registry (optional)
├── memory.json                      # Persistent agent memory
├── requirements.txt
├── framework/
│   ├── core/
│   │   ├── agent.py                 # LangGraph ReAct agent
│   │   ├── config.py                # Config loader
│   │   ├── context_manager.py       # Tool param correction/locking
│   │   ├── conversation_logger.py   # Per-run markdown logs
│   │   ├── graph_email_client.py    # Microsoft Graph API client
│   │   └── memory.py                # Persistent memory (JSON)
│   ├── events/
│   │   ├── base.py                  # Event + EventSource base classes
│   │   └── graph_email_event.py     # Graph API email polling source
│   ├── tools/
│   │   ├── email_parser.py
│   │   ├── cloudwatch_fetcher.py
│   │   ├── log_group_discovery.py
│   │   ├── dependency_checker.py
│   │   ├── graph_email_tools.py     # LangChain @tool wrappers for Graph API
│   │   ├── teams_notifier.py        # MS Teams Adaptive Card notifier
│   │   ├── service_registry.py      # (available, not registered)
│   │   └── comprehensive_validator.py # (available, not registered)
│   └── skills/
│       ├── investigation-summary/
│       ├── cloudwatch-fetcher/
│       ├── dependency-checker/
│       ├── log-group-discovery/
│       ├── email-parser/
│       ├── service-registry/
│       └── teams-notifier/
├── tests/
│   └── run_evals.py
└── logs/                            # Per-run investigation markdown files
```

## Requirements

- Python 3.11+
- AWS credentials with CloudWatch + Resource Explorer permissions
- Microsoft 365 app registration with `Mail.Read` and `Mail.ReadWrite` permissions
- Microsoft Teams Incoming Webhook URL

```bash
pip install -r requirements.txt
```

## Configuration (`config.yaml`)

```yaml
bedrock:
  model_id: "apac.amazon.nova-lite-v1:0"
  region: "ap-south-1"
  access_key_id: "..."
  secret_access_key: "..."
  session_token: "..."

email:
  tenantId: "..."
  clientId: "..."
  clientSecret: "..."
  userId: "mailbox@yourdomain.com"
  poll_interval: 60       # seconds
  subject_filter: "ALARM"

aws:
  access_key_id: "..."
  secret_access_key: "..."
  session_token: "..."
  region: ap-south-1

teams:
  webhook_url: "https://your-org.webhook.office.com/..."
  enabled: true

agent:
  max_iterations: 10
  memory_file: "memory.json"
  verbose: true
```

> Never commit real credentials. Rotate any exposed keys immediately.

## Usage

```bash
# Production — polls mailbox every 60s
python main.py

# Smoke test with a built-in sample alarm
python main.py --test

# Interactive chat mode
python main.py --interactive

# Backfill historical emails (last 3 days)
python backfill_graph_emails.py

# Test Graph API connection
python test_graph_api.py --list
python test_graph_api.py --read <message_id>

# Full integration test
python test_full_integration.py
```

## Investigation Flow

1. `parse_aws_alert_email` — extract alarm name, timestamp, region
2. `discover_log_group` — find best CloudWatch log group
3. `fetch_cloudwatch_logs` — fetch ERROR logs around alarm timestamp
4. `check_service_dependencies` — fetch logs for dependent services
5. Generate structured investigation summary
6. `notify_teams` — post summary to Teams with auto-inferred severity

## Severity Inference

Severity is auto-inferred from the investigation summary content — the LLM does not choose it:

| Severity | Triggered by |
|----------|-------------|
| Critical | outage, down, unavailable, fatal, crash, 500 errors |
| High | default — alarm fired with errors present |
| Medium | threshold crossed but no log evidence of errors |
| Low | resolved, OK state, no errors found |

## AWS Permissions Required

```json
{
  "Effect": "Allow",
  "Action": [
    "logs:FilterLogEvents",
    "resource-explorer-2:Search"
  ],
  "Resource": "*"
}
```

## Microsoft Graph API Permissions Required

- `Mail.Read`
- `Mail.ReadWrite` (to mark emails as read)

## Troubleshooting

- **No logs returned**: verify `alarm_timestamp` is passed, increase `minutes_back`, check log group and region
- **Log group discovery fails**: ensure Resource Explorer is enabled and indexed in your AWS account
- **Graph API 400 errors**: OData `contains()` filter is not supported — the client falls back to client-side filtering automatically
- **Expired token errors**: AWS session tokens expire; update credentials in `config.yaml`
- **Daemon exits immediately**: ensure `email.userId` is set in `config.yaml`
- **Teams card not appearing**: verify `teams.webhook_url` is set and the connector is active in your channel
