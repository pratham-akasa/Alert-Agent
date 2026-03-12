# AWS Alert Bot Project Flow

This document explains the full flow of the `Alert-Agent` project: architecture, runtime behavior, features, tools, skills, and test coverage.

## 1. Project Purpose

`Alert-Agent` is an autonomous AWS CloudWatch alarm investigation agent.  
It ingests alarm notifications (primarily from email), runs investigation tools, and produces a structured summary for operators.

Core goals:
- Parse incoming AWS alarm emails
- Identify the impacted service and log groups
- Fetch relevant CloudWatch logs around alarm time
- Check dependency services for correlated failures
- Produce actionable investigation summaries
- Persist history and corrections for future runs

---

## 2. High-Level Architecture

Main components:
1. **Entrypoint + Runtime Orchestration**: `main.py`
2. **Core Agent System**: `framework/core/agent.py`
3. **Event Sources**: `framework/events/*`
4. **Tooling Layer**: `framework/tools/*`
5. **Context + Memory + Logging**: `framework/core/context_manager.py`, `memory.py`, `conversation_logger.py`
6. **Skill Documents**: `framework/skills/*/SKILL.md`
7. **Configuration**: `config.yaml`, optional `services.yaml`

Request flow (simplified):
1. Email (IMAP polling) creates an `Event`
2. Agent receives event and runs ReAct loop
3. Agent calls tools in sequence (parse -> discover -> fetch -> dependencies)
4. Context manager locks key values and corrects drift
5. Final structured investigation summary is generated
6. Run details are saved to `logs/` and memory is updated

---

## 3. Runtime Modes (`main.py`)

`main.py` supports three modes:

1. **Daemon mode** (default):  
   Starts configured event sources (currently email source if credentials are present) and processes incoming alerts continuously.

2. **Test mode** (`python main.py --test`):  
   Sends a built-in sample AWS alarm event through the full agent pipeline.

3. **Interactive mode** (`python main.py --interactive`):  
   Lets you send free-text prompts to the same agent loop for debugging/manual investigations.

Startup steps:
1. Load `Config` from `config.yaml`
2. Build `Memory`
3. Register enabled tools (`ALL_TOOLS`)
4. Construct `Agent(config, tools, memory)`
5. Run selected mode

---

## 4. Event System (`framework/events`)

### 4.1 `Event` (`framework/events/base.py`)
- Standard object with:
  - `source` (e.g., `email`)
  - `event_type` (e.g., `aws_alarm`)
  - `payload` (subject/from/body)
  - `timestamp`

### 4.2 `EventSource` base class
- Abstract async event producer.
- Any source must implement `start()` and emit events via callback.

### 4.3 `EmailEventSource` (`framework/events/email_event.py`)
Features:
- Polls IMAP on interval
- Filters by unread + subject pattern (default `ALARM`)
- Decodes headers and extracts text body
- Emits standardized `Event`
- Marks processed emails as seen

---

## 5. Core Agent Flow (`framework/core/agent.py`)

### 5.1 Agent Initialization
- Creates local Ollama chat model (`ChatOllama`)
- Loads all skill docs from `framework/skills/*/SKILL.md`
- Injects memory context and correction history into system prompt
- Wraps tools with context-aware guardrails
- Creates LangGraph ReAct agent (`create_react_agent`)

### 5.2 Event Processing (`process_event`)
Main path:
1. Clear previous context for new event
2. Format event payload as user message
3. Invoke ReAct agent with recursion/iteration limit
4. Track which tools were used
5. If required investigation tools were skipped, force continuation with follow-up instruction
6. If final output misses required summary format, force a summary-only follow-up
7. Save full run to markdown log (`logs/*.md`)
8. Save event summary metadata to memory (`memory.json`)

### 5.3 Mandatory Investigation Logic (Prompt-enforced)
Expected sequence:
1. `parse_aws_alert_email`
2. `discover_log_group`
3. `fetch_cloudwatch_logs`
4. `check_service_dependencies`
5. Generate final structured investigation summary

### 5.4 Correction Learning Tool
- `store_correction(alarm_name, correction)`
- Saves user/operator corrections into persistent memory for future investigations

---

## 6. Context Guardrails (`framework/core/context_manager.py`)

Purpose: prevent value drift/hallucinated parameter changes across tool calls.

Key functionality:
- Locks key extracted values:
  - `alarm_name`
  - `alarm_timestamp`
  - `log_group_name`
- Stores raw output strings for downstream validation tools
- Validates and auto-corrects tool params:
  - wrong `alarm_name`
  - wrong log group value
  - wrong param name (`log_group` -> `log_group_name`)
  - invalid timestamp format for time-sensitive tools
- Can auto-inject missing validation payloads for comprehensive validator

---

## 7. Tooling Layer (`framework/tools`)

## 7.1 `parse_aws_alert_email` (`email_parser.py`)
Features:
- Parses JSON-style SNS payloads when present
- Falls back to regex extraction for text-format emails
- Extracts alarm details: alarm name, state, reason, region, account, timestamp, metric, etc.
- Performs validation checks for timestamp and region format
- Returns structured JSON string

## 7.2 `discover_log_group` + `search_log_groups` (`log_group_discovery.py`)
Features:
- Uses AWS Resource Explorer (`resource-explorer-2`)
- Derives prioritized search queries from alarm name
- Filters to `/copilot/` log groups
- Ranks production log groups first (`prod` preference)
- Returns best match + candidates + search trace

## 7.3 `fetch_cloudwatch_logs` (`cloudwatch_fetcher.py`)
Features:
- Uses CloudWatch Logs `filter_log_events`
- Supports filter pattern, window size, max events
- Uses `alarm_timestamp` if provided (critical for correct investigation window)
- Returns fetched events + validation metadata + AWS console deep link

## 7.4 `check_service_dependencies` (`dependency_checker.py`)
Features:
- Extracts primary service from alarm name
- Reads dependency knowledge base from:
  `framework/skills/service-registry/references/service_dependencies_kb.md`
- Finds dependency log groups via smart query search
- Fetches ERROR logs for each dependency in same incident window
- Produces per-dependency results + aggregate summary

## 7.5 `fetch_service_info` (`service_registry.py`) (optional in main tool list)
Features:
- Loads `services.yaml`
- Maps alarms to service metadata (owner team, log groups, dependencies, runbook, etc.)
- Supports lookup by alarm or service name
- Caches registry data for repeated calls

## 7.6 `notify_teams` (`teams_notifier.py`) (currently disabled in `main.py`)
Features:
- Builds Adaptive Card payload
- Sends summary to Microsoft Teams webhook
- Severity-aware styling and contextual metadata

## 7.7 `validate_investigation_logs` (`comprehensive_validator.py`) (currently disabled in `main.py`)
Features:
- Validates primary + dependency log fetch windows
- Checks alarm timestamp alignment across services
- Flags critical timing/consistency issues
- Produces pass/fail report and critical issue summary

---

## 8. Skills (`framework/skills/*/SKILL.md`)

The agent dynamically loads all skill files and injects them into its system context.

Current skill folders:
1. `email-parser`
2. `cloudwatch-fetcher`
3. `log-group-discovery`
4. `dependency-checker`
5. `service-registry`
6. `teams-notifier`
7. `investigation-summary`
8. `comprehensive-validator`

What skills provide:
- Operational constraints and best practices for each tool
- Investigation formatting requirements
- Domain-specific workflow guidance

Impact:
- Skills serve as instruction overlays for the LLM and significantly shape tool usage and output quality.

---

## 9. Memory, Logging, and Learning

### 9.1 Persistent Memory (`framework/core/memory.py`)
Stores:
- `facts`: key-value persistent facts
- `history`: recent processed events
- `corrections`: alarm-specific learned corrections

Backed by: `memory.json`

### 9.2 Conversation Logging (`framework/core/conversation_logger.py`)
For each run, writes a markdown file in `logs/` containing:
- Input event content
- Tool call inputs/outputs
- Final response
- Duration
- Hallucination warning heuristics (e.g., fabricated errors when event_count is 0)

---

## 10. Configuration and Environment

### 10.1 `config.yaml`
Primary config domains:
- `ollama`: model and endpoint
- `email`: IMAP settings and polling behavior
- `aws`: credentials + region
- `teams`: webhook settings
- `agent`: iteration limits, memory file path, verbosity

### 10.2 `framework/core/config.py`
Capabilities:
- Repo-root discovery (`get_repo_root`)
- Typed dotted-key lookup
- Central path helpers for `config.yaml` and `services.yaml`

### 10.3 `services.yaml`
- Optional static service registry file
- Current repository version is mostly commented template content

Security note:
- Keep AWS credentials and webhook URLs out of version control and rotate exposed credentials immediately if leaked.

---

## 11. Testing and Evaluation

### 11.1 Golden Cases (`tests/golden_evals.py`)
- Canonical alarm inputs and expected parser/registry outputs
- Intended for regression detection

### 11.2 Eval Runner (`tests/run_evals.py`)
Runs:
1. Tool-level evaluations
2. Optional agent-level evaluations (`--agent`, requires local Ollama)

Checks include:
- Email parser correctness
- Service registry lookup correctness
- Memory correction behavior
- Teams card payload shape

### 11.3 Local Fix Validation Script (`test_fixes.py`)
- Sanity checks for config path resolution, skill loading, imports, and validation helper behavior

---

## 12. Enabled vs Disabled Capabilities (Current State)

Enabled in `main.py` tool registry:
1. `parse_aws_alert_email`
2. `fetch_cloudwatch_logs`
3. `discover_log_group`
4. `search_log_groups`
5. `check_service_dependencies`

Commented/disabled in current `main.py`:
1. `validate_investigation_logs`
2. `fetch_service_info`
3. `notify_teams`

This means runtime investigations currently focus on parse/discover/logs/dependencies and local summary generation, without built-in final validation step or outbound Teams notifications by default.

---

## 13. End-to-End Sequence Example

1. CloudWatch alarm email arrives in monitored inbox.
2. `EmailEventSource` polls IMAP, finds unread `ALARM` email, emits `Event`.
3. `Agent.process_event()` formats event payload and starts ReAct loop.
4. Agent calls parser to extract alarm metadata.
5. Agent discovers best service log group via Resource Explorer.
6. Agent fetches primary service logs near alarm timestamp.
7. Agent checks dependency services and fetches their logs.
8. Context manager locks/corrects critical values during tool calls.
9. Agent writes final structured investigation summary.
10. Conversation logger writes run log in `logs/`.
11. Memory records summarized event metadata in `memory.json`.

---

## 14. Practical Extension Points

1. Re-enable `validate_investigation_logs` for stronger reliability checks.
2. Re-enable `fetch_service_info` with a populated `services.yaml`.
3. Re-enable `notify_teams` once webhook is configured.
4. Add new event sources (SNS/webhook/queue) by implementing `EventSource`.
5. Expand dependency KB and golden evals from real incidents.
6. Move secrets to environment variables or a secret manager.

