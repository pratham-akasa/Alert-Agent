# Alert Agent

Autonomous Python agent for investigating AWS CloudWatch alarms from email alerts.

It parses alarm emails, discovers relevant CloudWatch log groups, fetches logs around the alarm timestamp, checks known dependencies, and writes investigation runs to local markdown logs.

## What This Repo Currently Does

- Runs a LangGraph ReAct agent backed by `ChatOllama`
- Supports 3 modes:
  - daemon email polling mode (`python main.py`)
  - smoke test mode (`python main.py --test`)
  - interactive prompt mode (`python main.py --interactive`)
- Stores memory and corrections in `memory.json`
- Writes per-run investigation logs into `logs/`
- Uses AWS APIs for:
  - CloudWatch Logs (`logs:FilterLogEvents`)
  - Resource Explorer (`resource-explorer-2:Search`)

## Active Tools (Registered in `main.py`)

- `parse_aws_alert_email`
- `fetch_cloudwatch_logs`
- `discover_log_group`
- `search_log_groups`
- `check_service_dependencies`

Also available in `framework/tools/` but currently not registered in `main.py`:
- `fetch_service_info`
- `notify_teams`
- `validate_investigation_logs`

## Architecture

```text
Email (IMAP) -> EventSource -> Agent (LangGraph + Ollama) -> Tools (AWS + parsing)
                                              |
                                              +-> Memory (memory.json)
                                              +-> Run logs (logs/*.md)
```

## Project Structure

```text
.
├── main.py
├── config.yaml
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── framework/
│   ├── core/
│   │   ├── agent.py
│   │   ├── config.py
│   │   ├── context_manager.py
│   │   ├── conversation_logger.py
│   │   └── memory.py
│   ├── events/
│   │   ├── base.py
│   │   └── email_event.py
│   ├── tools/
│   │   ├── email_parser.py
│   │   ├── log_group_discovery.py
│   │   ├── cloudwatch_fetcher.py
│   │   ├── dependency_checker.py
│   │   ├── service_registry.py
│   │   ├── teams_notifier.py
│   │   └── comprehensive_validator.py
│   └── skills/
│       ├── investigation-summary/
│       └── ...
├── tests/
│   ├── run_evals.py
│   └── golden_evals.py
└── services.yaml
```

## Requirements

- Python 3.9+
- Ollama running locally or reachable over network
- AWS credentials with required permissions
- IMAP credentials (only for daemon email polling mode)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Main config file: `config.yaml`

Sections used by the app:
- `ollama.base_url`, `ollama.model`
- `email.*` (daemon mode)
- `aws.*`
- `agent.max_iterations`, `agent.memory_file`, `agent.verbose`
- `teams.*` (only used if Teams tool is enabled)

### Important Security Note

Do not commit real secrets (AWS keys, session tokens, email passwords, webhook URLs) into `config.yaml`.
Use environment variables or secret management in production.

## Usage

Run daemon (email polling):

```bash
python main.py
```

Run smoke test with sample alarm event:

```bash
python main.py --test
```

Run interactive mode:

```bash
python main.py --interactive
```

Use custom config path:

```bash
python main.py --config /absolute/path/to/config.yaml
```

## How Investigations Flow

1. Parse alarm email body (`parse_aws_alert_email`)
2. Discover best log group (`discover_log_group`)
3. Fetch primary logs (`fetch_cloudwatch_logs`)
4. Check dependency logs (`check_service_dependencies`)
5. Generate final summary response

The agent prompt strongly enforces using the alarm timestamp for log queries.

## Testing

Run tool-level evaluations:

```bash
python tests/run_evals.py
```

Run tool-level + agent-level evaluations (requires Ollama):

```bash
python tests/run_evals.py --agent
```

## Docker

Build and run with Compose:

```bash
docker compose up --build
```

Services defined:
- `ollama`
- `alert-bot`

The compose file mounts:
- `./logs:/app/logs`
- `./memory.json:/app/memory.json`
- `./config.yaml:/app/config.yaml`
- `./services.yaml:/app/services.yaml`

## AWS Permissions

Minimum IAM actions used by active tools:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "resource-explorer-2:Search"
      ],
      "Resource": "*"
    }
  ]
}
```

## Notes on Optional Files

- `services.yaml`: used by service registry tooling; currently template/commented data
- `framework/skills/service-registry/references/service_dependencies_kb.md`: dependency mapping source used by `check_service_dependencies`
- `clear_cache.sh`: convenience script to clear local caches/memory

## Troubleshooting

- No logs returned:
  - verify `alarm_timestamp` is passed into log fetches
  - increase `minutes_back`
  - verify log group and region
- Log group discovery fails:
  - check Resource Explorer is enabled and indexed
  - verify IAM permission `resource-explorer-2:Search`
- Daemon mode exits with no sources:
  - set `email.username` in `config.yaml`
- Ollama issues:
  - verify `ollama serve` is running
  - verify model exists (for example `qwen2.5:7b`)
