# AWS Alert Bot — Project Flow

## 1. Purpose

Autonomous AWS CloudWatch alarm investigation agent.

Reads alarm emails from a Microsoft 365 mailbox via Graph API, runs investigation tools against AWS, produces a structured summary, and posts it to a Microsoft Teams channel.

---

## 2. Runtime Modes (`main.py`)

| Mode | Command | Description |
|------|---------|-------------|
| Daemon | `python main.py` | Polls mailbox every 60s, processes alarms continuously |
| Test | `python main.py --test` | Runs a built-in sample alarm through the full pipeline |
| Interactive | `python main.py --interactive` | Free-text chat with the agent for manual investigations |
| Backfill | `python backfill_graph_emails.py` | Process historical emails from last N days |

---

## 3. Email Ingestion (Graph API)

**File**: `framework/events/graph_email_event.py`  
**Client**: `framework/core/graph_email_client.py`

Flow:
1. `GraphEmailEventSource.start()` runs an async polling loop
2. Every `poll_interval` seconds, calls `GraphEmailClient.list_messages()`
3. Filters unread emails with `subject_filter` ("ALARM") client-side
4. For each new message, calls `GraphEmailClient.read_message(message_id)`
5. Strips HTML from body via `extract_body_text()` → plain text
6. Emits `Event(source="graph_email", event_type="aws_alarm", payload={...})`
7. Marks email as read via `GraphEmailClient.mark_as_read()`

Authentication: OAuth2 client credentials flow  
Token endpoint: `https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token`

---

## 4. Agent Processing (`framework/core/agent.py`)

### 4.1 Initialization
- Loads `config.yaml` via `Config`
- Loads `memory.json` via `Memory`
- Loads all `framework/skills/*/SKILL.md` files into system prompt
- Wraps all tools with context-correction layer
- Creates LangGraph ReAct agent with `ChatBedrock` (Amazon Bedrock)

### 4.2 Event Processing (`process_event`)
1. Clear `ContextManager` state for new event
2. Format event as user message (JSON payload)
3. Invoke ReAct agent loop (max 10 iterations)
4. Check which required tools were used — if any missing, send follow-up
5. Check if `alarm_timestamp` was passed to log tools — if not, force retry
6. Check if final response contains investigation summary — if not, force summary
7. Save full run to `logs/<timestamp>_aws_alarm.md`
8. Append event summary to `memory.json`

### 4.3 Mandatory Investigation Sequence (prompt-enforced)
```
1. parse_aws_alert_email       → extract alarm_name, timestamp, region
2. discover_log_group          → find best CloudWatch log group
3. fetch_cloudwatch_logs       → fetch ERROR logs around alarm timestamp
4. check_service_dependencies  → fetch logs for all dependent services
5. Generate investigation summary (mandatory format)
6.  auto-inferred)
```



 + Context Manager

re/context_manager.py`

Eve intercepted:
```
Agent calls tool(pams)
    → Tool Wrapper
        → context_manager.validate_and_co
        → original_tool(corrected_params)
        → context_manager.updal, result)
   agent
```

Values locked after each step:
- `alarm_name` — locked after `parse_aws_alert_email`
- `alarm_timestamp` — locked after `parse_aws_alert_email`
- `log_group_name` — locked after `discover_log_group`
- `primary_logs_response` — locked after `fetch_cloudwatch_logs`
_service_dependencies`

Auto-corrections applied:
- Wrong param name (`log_group` → `log_group_n
- Missing `alarm_timestamp` on log fetch calls
ted `alarm_name` values

---

. Tools

ered in `main.py`)

| Tool | File | Purpose |
|------|------|---------|
| `parse_aws_alert_email` | `email_parser.py` | Extract alarm details from email body (plain text or HTML-stripped) |
| `discover_log_group` | `log_group_discovery.py` | Find best CloudWatch loglorer |
| `search_log_groups` | `log_group_discovery.py` | Manual log group search |
| `fetch_cloudwatch_logs` | `cloudwatch_fetcher.py` | Fetch logs from CloudWatch around alarm timeamp |
| `check_service_dependencies` | `dependency_checker.py` | Fetch logs for all dependent services |
| `list_graph_emails` | `graph_email_tools.py` | List unread alarm emails via Graph API |
| `read_graph_email` | `graph_email_tools.py` | Read full email content by e ID |
 Adaptive Card |
| `store_correction` | `agent.pymory |

### Available but not registered

| Tool | File | Notes |
|------|------|-------|
| `fetch_service_info` | `service_registry.py` | Needs `services.yaml` populated |
ation step |

---

fication

_notifier.py`

Called as the final mandatory step after the investigation summary is generated.

oes not choose it:

| Severity | Triggered by |
|----------|-------------|
| Critical | outage, down, unavailable, fatal, crash, 500 errors |
| High | default — alarm fired with errors present |
| Medium | threshold crossed but no log evidence of errors |
ors found |

y
- Posts to the configureng Webhook
y if no webhook URL is configured (logs a warning, does not crash)

---

## 8. Email Parser Detail

tools/email_parser.py`

Handles two email formats:
1. **JSON SNS pils with embedded JSON
2. **Plain text / HTML-stripped** — forwarails stripped to single-line text

Key parsing approach for plain text:
- Region: direct strin"ap-south-1"`)
- Timestam UTC (won't over-capture)
Name: value` patterns
- Rseparator
undary)





### `memory.json`
Three sections:
- `facts` — explicit key-value facts stored by agent
- `history` — last 200 processed event summaries with timestamps
- `corrections` — per-alarm corrections stored via ion` tool

t.

### `logs/*.md`
ntaining:
- Iput event payload

- Final agent response


---

## 10. Configuration

### `config.yaml` sections

| Section | Used by |
|---------|---------|
| `bedrock` | Agent LLM (model, region, credentials) |
| `email` | Graph API polling (tenantId, clientId, clientSecret, userId) |
| `aws` | CloudWatch + Resource Explorer (credentials, region) |
| `teams` | Teams notifier (webhook_url, enabled) |
| `agent` | max_iterations, memory_file, verbose |

### `services.yaml`
Optabled.
 as read
```
rd posted to Teams
12. logs/2026-03-18_04-08-xx_aws_alarm.md written
13. memory.json updated with event summary
14. Email marked", Adaptive Carred as "Highfy_teams → severity auto-infed investigation summary
11. notitc.
10. Agent generates structurek_service_dependencies → checks data-transfer-service, dcs-service, eRROR events around 04:08 UTC
9.  chec
8.  fetch_cloudwatch_logs → 15 Epilot/qp-prod-qp-booking-webservice" → best_log_group="/co-south-1"
7.  discover_log_group               region="apUTC",
                 026 04:08:18 sday 18 March, 2estamp="Tue                           timg-service-common-error",
   → alarm_name="qp-bookin6.  parse_aws_alert_emailts ReAct loop
.process_event() starssageId
5.  Agentm, body, ment with subject, froody
4.  Emits Eveage, strips HTML → plain text beads full messread ALARM email
3.  RventSource polls Graph API → finds unlbox
2.  GraphEmailES sends email to mai`
1.  CloudWatch alarm fires → SNnd-to-End Example

``
---

## 11. E