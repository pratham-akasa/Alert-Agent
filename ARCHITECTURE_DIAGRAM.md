# Auto-Injection Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           LangGraph Agent                            │
│                     (ReAct Loop - Unreliable)                        │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             │ Tool Call Request
                             │ (may have wrong params)
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         Tool Wrapper Layer                           │
│                    (Intercepts ALL tool calls)                       │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ 1. Receive tool call with parameters                       │    │
│  │    Example: validate_investigation_logs(                   │    │
│  │      primary_logs_response="",  ← Empty!                   │    │
│  │      dependency_logs_response=""  ← Empty!                 │    │
│  │    )                                                        │    │
│  └────────────────────────────────────────────────────────────┘    │
│                             ↓                                        │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ 2. Call Context Manager to validate & correct params       │    │
│  └────────────────────────────────────────────────────────────┘    │
│                             ↓                                        │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ 3. Execute tool with CORRECTED parameters                  │    │
│  │    Example: validate_investigation_logs(                   │    │
│  │      primary_logs_response="{...1234 chars...}",  ← Fixed! │    │
│  │      dependency_logs_response="{...5678 chars...}"  ← Fixed!│   │
│  │    )                                                        │    │
│  └────────────────────────────────────────────────────────────┘    │
│                             ↓                                        │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ 4. Store tool output in Context Manager                    │    │
│  └────────────────────────────────────────────────────────────┘    │
│                             ↓                                        │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ 5. Return result to agent                                  │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        Context Manager                               │
│                   (Stores & Corrects Data)                           │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │ Locked Values (Immutable)                                 │      │
│  │ ─────────────────────────────                             │      │
│  │ • alarm_name: "qp-booking-service-common-error"           │      │
│  │ • alarm_timestamp: "Tuesday 10 March, 2026 14:08:18 UTC"  │      │
│  │ • log_group_name: "/copilot/qp-prod-qp-booking-webservice"│      │
│  │ • primary_logs_response: "{...1234 chars...}" 🔒          │      │
│  │ • dependency_logs_response: "{...5678 chars...}" 🔒       │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │ Raw Outputs (Full JSON Strings)                           │      │
│  │ ───────────────────────────────                           │      │
│  │ • parse_aws_alert_email_output: "{...}"                   │      │
│  │ • discover_log_group_output: "{...}"                      │      │
│  │ • fetch_cloudwatch_logs_output: "{...}"                   │      │
│  │ • check_service_dependencies_output: "{...}"              │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │ Correction Logic                                          │      │
│  │ ────────────────                                          │      │
│  │ IF tool == "validate_investigation_logs":                 │      │
│  │   IF primary_logs_response is empty:                      │      │
│  │     → Inject from locked_values["primary_logs_response"]  │      │
│  │   IF dependency_logs_response is empty:                   │      │
│  │     → Inject from locked_values["dependency_logs_response"]│     │
│  │   IF alarm_timestamp is missing:                          │      │
│  │     → Inject from locked_values["alarm_timestamp"]        │      │
│  └──────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow Timeline

```
Time  │ Event                                    │ Context State
──────┼──────────────────────────────────────────┼─────────────────────────
T0    │ Agent starts investigation               │ Empty
      │                                          │
T1    │ parse_aws_alert_email()                  │ 🔒 alarm_name
      │ → Returns: {alarm_name, timestamp, ...}  │ 🔒 alarm_timestamp
      │                                          │
T2    │ discover_log_group()                     │ 🔒 alarm_name
      │ → Returns: {best_log_group, ...}         │ 🔒 alarm_timestamp
      │                                          │ 🔒 log_group_name
      │                                          │
T3    │ fetch_cloudwatch_logs()                  │ 🔒 alarm_name
      │ → Returns: {log_group, events, ...}      │ 🔒 alarm_timestamp
      │ → Stored as primary_logs_response        │ 🔒 log_group_name
      │                                          │ 🔒 primary_logs_response ✨
      │                                          │
T4    │ check_service_dependencies()             │ 🔒 alarm_name
      │ → Returns: {dependency_results, ...}     │ 🔒 alarm_timestamp
      │ → Stored as dependency_logs_response     │ 🔒 log_group_name
      │                                          │ 🔒 primary_logs_response
      │                                          │ 🔒 dependency_logs_response ✨
      │                                          │
T5    │ validate_investigation_logs(             │ 🔒 All values available
      │   primary_logs_response="",  ← Empty!    │
      │   dependency_logs_response=""  ← Empty!  │
      │ )                                        │
      │ ↓ Tool Wrapper Intercepts                │
      │ ↓ Context Manager Detects Empty          │
      │ ↓ AUTO-INJECT from T3 & T4               │ ⚠️ AUTO-INJECTING...
      │ ↓ Execute with correct params            │
      │ → Returns: {validation_report}           │ ✅ Validation complete
```

## Component Interaction

```
┌──────────────┐
│   Agent.py   │
└──────┬───────┘
       │
       │ 1. Initialize with tools
       ↓
┌──────────────────────────────────────┐
│ _wrap_tools_with_context()          │
│                                      │
│ For each tool:                       │
│   Create wrapper function that:      │
│   • Calls context_manager.validate() │
│   • Executes original tool           │
│   • Calls context_manager.update()   │
│   • Returns result                   │
└──────┬───────────────────────────────┘
       │
       │ 2. Wrapped tools used by agent
       ↓
┌──────────────────────────────────────┐
│ LangGraph ReAct Agent                │
│                                      │
│ Calls tools with (possibly wrong)    │
│ parameters                           │
└──────┬───────────────────────────────┘
       │
       │ 3. Tool call intercepted
       ↓
┌──────────────────────────────────────┐
│ Tool Wrapper                         │
│                                      │
│ wrapped_func(**kwargs):              │
│   corrected = context_manager        │
│     .validate_and_correct_params()   │────┐
│   result = original_func(            │    │
│     **corrected)                     │    │
│   context_manager                    │    │
│     .update_from_tool_output()       │────┤
│   return result                      │    │
└──────────────────────────────────────┘    │
                                            │
       ┌────────────────────────────────────┘
       │
       ↓
┌──────────────────────────────────────────────────────┐
│ Context Manager                                      │
│                                                      │
│ validate_and_correct_params(tool_name, params):     │
│   IF tool_name == "validate_investigation_logs":    │
│     IF params["primary_logs_response"] is empty:    │
│       params["primary_logs_response"] =             │
│         _locked_values["primary_logs_response"]     │
│     IF params["dependency_logs_response"] is empty: │
│       params["dependency_logs_response"] =          │
│         _locked_values["dependency_logs_response"]  │
│   return corrected_params                           │
│                                                      │
│ update_from_tool_output(tool_name, output):         │
│   IF tool_name == "fetch_cloudwatch_logs":          │
│     _locked_values["primary_logs_response"] = output│
│   IF tool_name == "check_service_dependencies":     │
│     _locked_values["dependency_logs_response"] =    │
│       output                                        │
└──────────────────────────────────────────────────────┘
```

## Before vs After

### Before (Broken)
```
Agent → validate_investigation_logs(
          primary_logs_response="",
          dependency_logs_response=""
        )
        ↓
        Tool executes with empty strings
        ↓
        ❌ Error: "Expecting value: line 1 column 1 (char 0)"
```

### After (Fixed)
```
Agent → validate_investigation_logs(
          primary_logs_response="",
          dependency_logs_response=""
        )
        ↓
        Tool Wrapper intercepts
        ↓
        Context Manager detects empty params
        ↓
        Auto-inject from stored outputs
        ↓
        Tool executes with correct JSON strings
        ↓
        ✅ Validation report generated
```

## Key Design Principles

1. **Separation of Concerns**
   - Agent: Reasoning and decision making
   - Tool Wrapper: Interception and correction
   - Context Manager: Data storage and validation

2. **Fail-Safe Design**
   - Assume LLM will make mistakes
   - Programmatically enforce correctness
   - Log all corrections for debugging

3. **Transparency**
   - All corrections logged with ⚠️ warnings
   - Original parameters preserved for debugging
   - Clear audit trail of what was changed

4. **Non-Invasive**
   - Tools don't need modification
   - Tool signatures unchanged
   - Backward compatible

5. **Extensible**
   - Easy to add corrections for other tools
   - Easy to add new locked values
   - Easy to add new validation rules
