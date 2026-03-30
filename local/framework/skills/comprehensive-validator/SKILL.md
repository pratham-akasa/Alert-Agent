---
name: comprehensive-validator
description: "[DISABLED] Validates ALL log fetches in an investigation to ensure logs were fetched from correct time windows. Currently disabled due to parameter handling issues."
compatibility: Designed for comprehensive AWS alarm investigation validation
allowed-tools: comprehensive_validator
metadata:
  owner: platform-team
  version: "1.0"
  status: disabled
---

# Comprehensive Log Validation (DISABLED)

**⚠️ CURRENTLY DISABLED**: This skill is temporarily disabled due to parameter handling issues between the agent and the validation tool.

## Purpose
Validates ALL log fetches in an investigation - both primary service and all dependencies - to ensure logs were fetched from the correct time windows.

## Status
This skill has been removed from the active workflow to simplify the investigation process and avoid parameter passing issues.

## When it was used
- After completing log fetching steps (cloudwatch-fetcher and dependency-checker)
- Before providing final analysis
- As step 5 in the investigation workflow

## Why it was disabled
- Complex parameter passing requirements (string vs dictionary objects)
- Agent was not following the exact parameter format requirements
- Causing investigation workflow to fail or get stuck

## Future re-enablement
This skill may be re-enabled once the parameter handling issues are resolved and the agent can properly pass string parameters instead of dictionary objects.