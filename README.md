# AWS Alert Bot — Autonomous Agent

An intelligent AWS CloudWatch alarm investigation agent that automatically analyzes alerts, fetches logs, checks dependencies, and provides root cause analysis.

## 🎯 Overview

The AWS Alert Bot is an autonomous agent that:
- **Monitors email** for AWS CloudWatch alarm notifications
- **Automatically investigates** alarms by fetching relevant logs
- **Checks service dependencies** to identify root causes
- **Provides detailed analysis** with actionable solutions
- **Learns from corrections** to improve future investigations

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Email Source  │───▶│      Agent      │───▶│   Tools Suite   │
│   (IMAP Poll)   │    │   (LangChain)   │    │  (AWS + Logic)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │     Memory      │
                       │ (Persistent)    │
                       └─────────────────┘
```

### Core Components

1. **Agent** (`framework/agent.py`) - LangChain ReAct agent with Ollama LLM
2. **Event Sources** (`framework/events/`) - Email polling and event processing
3. **Tools Suite** (`framework/tools/`) - AWS API integrations and analysis tools
4. **Memory System** (`framework/memory.py`) - Persistent learning and context
5. **Configuration** (`config.yaml`) - Centralized settings management

## 🛠️ Tools Suite

### 1. Email Parser (`parse_aws_alert_email`)
**Purpose**: Parse AWS CloudWatch alarm emails and extract structured data

**Input**: Raw email body from AWS SNS/CloudWatch
**Output**: Structured alarm data (name, timestamp, region, etc.)

```python
parse_aws_alert_email(raw_email_body="You are receiving this email...")
# Returns: {"alarm_name": "qp-booking-service-common-error", "timestamp": "...", ...}
```

### 2. Log Group Discovery (`discover_log_group`)
**Purpose**: Automatically find the correct CloudWatch log group for an alarm

**Features**:
- Smart keyword extraction from alarm names
- Prioritized search queries
- Production environment preference
- AWS Resource Explorer integration

```python
discover_log_group(alarm_name="qp-booking-service-common-error")
# Returns: {"best_log_group": "/copilot/qp-prod-qp-booking-webservice", ...}
```

### 3. CloudWatch Logs Fetcher (`fetch_cloudwatch_logs`)
**Purpose**: Fetch log events from CloudWatch Logs with precise time windows

**Features**:
- Alarm timestamp-based queries (not current time)
- Configurable filter patterns
- Adjustable time windows
- Built-in validation metadata

```python
fetch_cloudwatch_logs(
    log_group_name="/copilot/qp-prod-qp-booking-webservice",
    filter_pattern="ERROR",
    minutes_back=10,
    alarm_timestamp="Monday 09 March, 2026 04:08:18 UTC"
)
```

### 4. Dependency Checker (`check_service_dependencies`)
**Purpose**: Automatically check all service dependencies for errors

**Features**:
- Knowledge base-driven dependency mapping
- Automatic log group discovery for dependencies
- Parallel log fetching from all dependencies
- Comprehensive error analysis

```python
check_service_dependencies(
    alarm_name="qp-booking-service-common-error",
    alarm_timestamp="Monday 09 March, 2026 04:08:18 UTC"
)
```

### 5. Service Registry (`fetch_service_info`)
**Purpose**: Look up service metadata, owners, and operational context

**Features**:
- Service-to-log-group mapping
- Team ownership information
- Dependency relationships
- Operational notes and runbooks

### 6. Teams Notifier (`notify_teams`)
**Purpose**: Send investigation results to Microsoft Teams channels

**Features**:
- Severity-based formatting
- Team-specific routing
- Rich card formatting
- Actionable summaries

### 7. Comprehensive Validator (`validate_investigation_logs`)
**Purpose**: Validate ALL services in an investigation (primary + dependencies)

**Features**:
- Validates primary service and all dependencies in one call
- Checks timestamp usage across all services
- Identifies critical timing issues
- Provides comprehensive validation report
- Ensures investigation reliability

## 🔄 Investigation Workflow

The agent follows a strict 6-step workflow for every alarm:

### Step 1: Parse Email
```
parse_aws_alert_email(raw_email_body) 
→ Extract: alarm_name, timestamp, region, account_id
```

### Step 2: Discover Log Group
```
discover_log_group(alarm_name) 
→ Find: best_log_group for the service
```

### Step 3: Fetch Primary Logs
```
fetch_cloudwatch_logs(
    log_group_name=<best_log_group>,
    alarm_timestamp=<timestamp>,
    filter_pattern="ERROR"
)
→ Get: Recent error logs from primary service
```

### Step 4: Check Dependencies
```
check_service_dependencies(
    alarm_name=<alarm_name>,
    alarm_timestamp=<timestamp>
)
→ Analyze: All dependency services for errors
```

### Step 5: Validate ALL Services
```
validate_investigation_logs(
    primary_logs_response=<step3_output>,
    dependency_logs_response=<step4_output>,
    alarm_timestamp=<timestamp>
)
→ Validate: ALL services (primary + dependencies) used correct time windows
```

### Step 6: Provide Analysis
```
Generate structured summary:
- Where it happened (services/log groups)
- What happened (specific errors)
- Why it happened (root cause)
- Possible solutions (actionable steps)
- Validation status (whether logs are reliable)
```

## 📁 Project Structure

```
├── main.py                          # Entry point and CLI
├── config.yaml                      # Configuration file
├── requirements.txt                 # Python dependencies
├── services.yaml                    # Service registry (optional)
├── memory.json                      # Persistent agent memory
├── logs/                           # Investigation logs
│   └── 2026-03-10_08-22-44_aws_alarm.md
├── framework/                      # Core framework
│   ├── agent.py                    # Main agent logic
│   ├── config.py                   # Configuration loader
│   ├── memory.py                   # Persistent memory system
│   ├── context_manager.py          # Context tracking
│   ├── conversation_logger.py      # Investigation logging
│   ├── events/                     # Event sources
│   │   ├── base.py                 # Event base classes
│   │   └── email_event.py          # Email polling source
│   └── tools/                      # Tool implementations
│       ├── email_parser.py         # AWS email parsing
│       ├── cloudwatch_fetcher.py   # Log fetching
│       ├── log_group_discovery.py  # Log group search
│       ├── dependency_checker.py   # Dependency analysis
│       ├── service_registry.py     # Service lookup
│       ├── teams_notifier.py       # Teams integration
│       ├── comprehensive_validator.py # Comprehensive validation
│       └── *_skill.md              # Tool documentation
```

## ⚙️ Configuration

### config.yaml
```yaml
# LLM Configuration
ollama:
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"

# Email Monitoring
email:
  imap_server: "outlook.office365.com"
  imap_port: 993
  folder: "INBOX"
  poll_interval: 60
  subject_filter: "ALARM"
  username: "your-email@company.com"
  password: "your-app-password"

# AWS Credentials
aws:
  access_key_id: "AKIA..."
  secret_access_key: "..."
  session_token: "..."  # Optional
  region: "ap-south-1"

# Agent Settings
agent:
  max_iterations: 20
  memory_file: "memory.json"
  verbose: true

# Teams Integration (Optional)
teams:
  webhook_url: "https://outlook.office.com/webhook/..."
  enabled: true
```

### Service Dependencies (framework/tools/service_dependencies_kb.md)
```markdown
# Knowledge Base: Service Dependencies

## qp-booking-webservice
- Nav-ods-Webservice
- data-transfer-service

## qp-payment-service
- qp-fraud-detection-service
- qp-bank-integration-service
```

## 🚀 Usage

### Production Mode (Email Monitoring)
```bash
python main.py
```
Continuously monitors email for AWS alarms and processes them automatically.

### Test Mode (Sample Alarm)
```bash
python main.py --test
```
Processes a built-in sample alarm for testing.

### Interactive Mode (Manual Chat)
```bash
python main.py --interactive
```
Chat directly with the agent for manual investigations.

### Custom Configuration
```bash
python main.py --config /path/to/custom-config.yaml
```

## 🧠 Intelligence Features

### Context Management
- **Value Locking**: Prevents parameter drift during investigations
- **Correction System**: Learns from user feedback
- **Memory Persistence**: Remembers past investigations and patterns

### Smart Log Discovery
- **Keyword Extraction**: Automatically extracts service names from alarms
- **Prioritized Search**: Uses multiple search strategies with fallbacks
- **Environment Preference**: Prefers production log groups

### Dependency Analysis
- **Automatic Discovery**: Finds log groups for all dependencies
- **Parallel Processing**: Fetches logs from multiple services simultaneously
- **Root Cause Detection**: Identifies if issues originate from dependencies

### Validation System
- **Time Window Validation**: Ensures logs are from alarm time, not current time
- **AWS Console Integration**: Generates URLs for manual verification
- **Comprehensive Checks**: Validates timestamps, event counts, and patterns

## 📊 Investigation Output

Each investigation produces a structured markdown report:

```markdown
# Agent Run — 2026-03-10 08:22:44 UTC

**Source**: email
**Type**: aws_alarm
**Duration**: 80.7s

## Input Event
[Original alarm email content]

## Tool Calls
### 1. parse_aws_alert_email
**Input**: [Raw email body]
**Output**: [Structured alarm data]

### 2. discover_log_group
**Input**: [Alarm name]
**Output**: [Best log group found]

### 3. fetch_cloudwatch_logs
**Input**: [Log group, filters, time window]
**Output**: [Log events from primary service]

### 4. check_service_dependencies
**Input**: [Alarm name, timestamp]
**Output**: [Dependency analysis with all logs]

## Final Response
🔍 INVESTIGATION SUMMARY

### 1. WHERE IT HAPPENED
- Primary Service: qp-booking-webservice
- Primary Log Group: /copilot/qp-prod-qp-booking-webservice
- Affected Dependencies: data-transfer-service

### 2. WHAT HAPPENED
- Error Type: UnrecognizedPropertyException
- Error Message: Unrecognized field "DelayReasonCode.Custom"
- Error Count: 50 occurrences
- Sample Error: [Actual error message from logs]

### 3. WHY IT HAPPENED (Root Cause)
- Root Cause: Data schema mismatch in DelayDetail class
- Contributing Factors: API contract change in upstream system

### 4. POSSIBLE SOLUTIONS
1. Update DelayDetail DTO to include DelayReasonCode.Custom field
2. Add @JsonIgnoreProperties(ignoreUnknown = true) to handle unknown fields
3. Implement data validation at API boundary
```

## 🔧 Advanced Features

### Memory System
The agent maintains persistent memory across sessions:

```python
# Store facts
memory.store("booking_service_batch_time", "04:00 UTC daily")

# Add corrections
memory.add_correction(
    "qp-booking-service-common-error",
    "This alarm fires during nightly batch jobs - usually safe to ignore"
)

# Recall context
context = memory.get_context_summary()
```

### Validation Tools
Comprehensive validation ensures accuracy:

```python
# Validate entire investigation (primary + dependencies)
from framework.tools.comprehensive_validator import validate_investigation_logs

validation = validate_investigation_logs(
    primary_logs_response=primary_logs,
    dependency_logs_response=dependency_logs,
    alarm_timestamp="Monday 09 March, 2026 04:08:18 UTC"
)

# Check validation results
if validation["overall_pass"]:
    print("✅ All services validated correctly")
else:
    print("❌ Validation failed:", validation["summary"]["critical_issues"])
```

### Custom Tool Development
Add new tools by following the pattern:

```python
from langchain_core.tools import tool

@tool
def my_custom_tool(param1: str, param2: int = 10) -> str:
    """
    Tool description for the LLM.
    
    Args:
        param1: Description of parameter
        param2: Optional parameter with default
    
    Returns:
        JSON string with results
    """
    # Implementation
    return json.dumps({"result": "success"})

# Register in main.py
ALL_TOOLS.append(my_custom_tool)
```

## 🐛 Troubleshooting

### Common Issues

**1. No events found in logs**
- Check if `alarm_timestamp_used` shows "current time" instead of actual alarm time
- Verify log group name matches the service
- Increase `minutes_back` parameter for wider time window

**2. Wrong log groups discovered**
- Update service dependencies in `service_dependencies_kb.md`
- Check AWS Resource Explorer permissions
- Verify log group naming conventions

**3. Email polling not working**
- Verify IMAP credentials in config.yaml
- Check email folder and subject filter settings
- Ensure app-specific passwords for Office 365

**4. Tool execution errors**
- Check AWS credentials and permissions
- Verify Ollama is running and accessible
- Review agent logs for detailed error messages

### Validation Commands

```bash
# Test AWS connectivity
aws logs describe-log-groups --region ap-south-1

# Test Ollama connectivity
curl http://localhost:11434/api/tags

# Validate configuration
python -c "from framework.core.config import Config; print(Config().ollama_model)"
```

## 📈 Performance & Scaling

### Optimization Tips
- **Concurrent Processing**: Tools run in parallel where possible
- **Smart Caching**: Memory system reduces redundant API calls
- **Efficient Queries**: Targeted log searches with appropriate time windows
- **Batch Operations**: Dependency checker processes multiple services simultaneously

### Resource Requirements
- **Memory**: ~500MB for typical workloads
- **CPU**: Moderate (depends on Ollama model size)
- **Network**: AWS API calls and email polling
- **Storage**: Log files and memory.json (grows over time)

## 🔒 Security Considerations

### Credentials Management
- Store AWS credentials securely (IAM roles preferred)
- Use app-specific passwords for email accounts
- Rotate credentials regularly
- Limit AWS permissions to minimum required

### Required AWS Permissions
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:DescribeLogGroups",
                "logs:FilterLogEvents",
                "resource-explorer-2:Search"
            ],
            "Resource": "*"
        }
    ]
}
```

## 🤝 Contributing

### Adding New Tools
1. Create tool implementation in `framework/tools/`
2. Add corresponding `*_skill.md` documentation
3. Register tool in `main.py` ALL_TOOLS list
4. Update this README with tool description

### Extending Event Sources
1. Inherit from `EventSource` base class
2. Implement `start()` method for event polling/listening
3. Emit `Event` objects via `self._emit(event)`
4. Register in `main.py` event sources

### Improving Intelligence
1. Enhance dependency mapping in knowledge base
2. Add service-specific investigation patterns
3. Improve error pattern recognition
4. Extend validation capabilities

## 📚 Additional Resources

- **Tool Skills** - Individual tool documentation in `framework/tools/*_skill.md`
- **Configuration** - See `config.yaml` for all settings
- **Service Dependencies** - Edit `framework/tools/service_dependencies_kb.md`

## 🏷️ Version History

- **v1.0** - Initial release with basic alarm processing
- **v1.1** - Added dependency checking and validation
- **v1.2** - Enhanced memory system and context management
- **v1.3** - Improved log discovery and timestamp handling
- **Current** - Comprehensive validation and documentation

---

**Built with**: Python 3.9+, LangChain, Ollama, AWS SDK, asyncio

**License**: MIT

**Maintainer**: DevOps Team

For support, create an issue or contact the DevOps team.