# Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Microsoft 365 Mailbox                       │
│              (internal.automations@akasaair.com)                │
└────────────────────────────┬────────────────────────────────────┘
                             │ OAuth2 (client credentials)
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                   GraphEmailEventSource                         │
│              (framework/events/graph_email_event.py)            │
│                                                                 │
│  • Polls every 60s via Microsoft Graph API                      │
│  • Filters unread emails with "ALARM" in subject                │
│  • Strips HTML → plain text via GraphEmailClient                │
│  • Marks processed emails as read                               │
│  • Emits Event(source="graph_email", type="aws_alarm")          │
└────────────────────────────┬────────────────────────────────────┘
                             │ Event
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph ReAct Agent                        │
│                  (framework/core/agent.py)                      │
│                                                                 │
│  Model: Amazon Bedrock (nova-lite) via ChatBedrock              │
│  Loop:  Think → Tool Call → Observe → Repeat                    │
│                                                                 │
│  System prompt includes:                                        │
│    • Mandatory 6-step investigation workflow                    │
│    • Skill documents (framework/skills/*/SKILL.md)              │
│    • Memory context (recent events + corrections)               │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Tool calls (intercepted by Tool Wrapper Layer)
       ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Tool Wrapper Layer                          │
│              (_wrap_tools_with_context in agent.py)             │
│                                                                 │
│  For every tool call:                                           │
│    1. context_manager.validate_and_correct_params()             │
│    2. Execute original tool with corrected params               │
│    3. context_manager.update_from_tool_output()                 │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ├──────────────────────────────────────────────────────────┐
       │                                                          │
       ↓                                                          ↓
┌──────────────────────┐                          ┌──────────────────────────┐
│   Email Tools        │                          │   Investigation Tools    │
│                      │                          │                          │
│ list_graph_emails    │                          │ parse_aws_alert_email    │
│ read_graph_email     │                          │ discover_log_group       │
│                      │                          │ search_log_groups        │
│ (Graph API calls     │                          │ fetch_cloudwatch_logs    │
│  via GraphEmailClient│                          │ check_service_dependencies│
│  in framework/core/) │                          │ store_correction         │
└──────────────────────┘                          └──────────┬───────────────┘
                                                             │
                                          ┌──────────────────┴──────────────────┐
                                          │                                     │
                                          ↓                                     ↓
                               ┌──────────────────┐               ┌────────────────────┐
                               │   AWS CloudWatch │               │  AWS Resource      │
                               │   Logs API       │               │  Explorer API      │
                               │                  │               │                    │
                               │ FilterLogEvents  │               │ Search log groups  │
                               └──────────────────┘               └────────────────────┘
       │
       ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Context Manager                            │
│              (framework/core/context_manager.py)                │
│                                                                 │
│  Locks and protects key values across tool calls:               │
│    🔒 alarm_name                                                │
│    🔒 alarm_timestamp                                           │
│    🔒 log_group_name                                            │
│    🔒 primary_logs_response                                     │
│    🔒 dependency_logs_response                                  │
│                                                                 │
│  Auto-corrects common LLM mistakes:                             │
│    • Wrong param names (log_group → log_group_name)             │
│    • Missing alarm_timestamp on log fetch calls                 │
│    • Drifted alarm_name values                                  │
└─────────────────────────────────────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Teams Notifier                              │
│              (framework/tools/teams_notifier.py)                │
│                                                                 │
│  • Auto-infers severity from summary content                    │
│    Critical → High → Medium → Low                               │
│  • Builds Adaptive Card with alarm name + severity + summary    │
│  • Posts to MS Teams channel via Incoming Webhook               │
└─────────────────────────────────────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Persistence Layer                           │
│                                                                 │
│  memory.json                  logs/*.md                         │
│  ─────────────                ────────────────────────          │
│  • facts (key-value)          • Full tool call trace            │
│  • history (last 200 events)  • Input/output per tool           │
│  • corrections (per alarm)    • Final investigation summary     │
│                               • Duration + metadata             │
└─────────────────────────────────────────────────────────────────┘
```

## Investigation Data Flow

```
Time │ Step                          │ Context State
─────┼───────────────────────────────┼──────────────────────────────────
T0   │ Email received (Graph API)    │ Empty
     │                               │
T1   │ parse_aws_alert_email()       │ 🔒 alarm_name
     │ → alarm_name, timestamp,      │ 🔒 alarm_timestamp
     │   region, metric              │
     │                               │
T2   │ discover_log_group()          │ 🔒 alarm_name
     │ → best_log_group              │ 🔒 alarm_timestamp
     │                               │ 🔒 log_group_name ✨
     │                               │
T3   │ fetch_cloudwatch_logs()       │ 🔒 alarm_name
     │ → log events around alarm     │ 🔒 alarm_timestamp
     │   timestamp                   │ 🔒 log_group_name
     │                               │ 🔒 primary_logs_response ✨
     │                               │
T4   │ check_service_dependencies()  │ 🔒 all above
     │ → dependency service logs     │ 🔒 dependency_logs_response ✨
     │                               │
T5   │ Investigation summary         │ ✅ All values available
     │   generated by agent          │
     │                               │
T6   │ notify_teams()                │ ✅ Summary posted to Teams
     │ → Adaptive Card posted        │    Severity auto-inferred
     │   logs/*.md written           │
     │   memory.json updated         │
```

## Component Map

```
framework/
├── core/
│   ├── agent.py               ← ReAct agent, tool wrapping, prompt
│   ├── config.py              ← Config loader (config.yaml)
│   ├── context_manager.py     ← Param locking + auto-correction
│   ├── conversation_logger.py ← Per-run markdown log writer
│   ├── graph_email_client.py  ← Microsoft Graph API HTTP client
│   └── memory.py              ← JSON-backed persistent memory
│
├── events/
│   ├── base.py                ← Event + EventSource abstractions
│   └── graph_email_event.py   ← Graph API polling event source
│
├── tools/
│   ├── email_parser.py        ← AWS alarm email parser
│   ├── cloudwatch_fetcher.py  ← CloudWatch Logs fetcher
│   ├── log_group_discovery.py ← Resource Explorer log group search
│   ├── dependency_checker.py  ← Dependency service log checker
│   ├── graph_email_tools.py   ← @tool wrappers for Graph API
│   ├── teams_notifier.py      ← Teams Adaptive Card notifier (active)
│   ├── service_registry.py    ← Service metadata lookup (optional)
│   └── comprehensive_validator.py ← Log validation (optional)
│
└── skills/
    ├── investigation-summary/ ← Summary format instructions
    ├── cloudwatch-fetcher/    ← CloudWatch usage guidance
    ├── dependency-checker/    ← Dependency check guidance
    ├── log-group-discovery/   ← Log group search guidance
    ├── email-parser/          ← Email parsing guidance
    ├── service-registry/      ← Service registry + dependency KB
    ├── teams-notifier/        ← Teams notification guidance
    └── comprehensive-validator/
```
