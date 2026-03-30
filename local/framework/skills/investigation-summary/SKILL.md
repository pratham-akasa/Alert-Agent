---
name: investigation-summary
description: Provides the exact format and structure for creating comprehensive investigation summaries after completing all AWS alarm investigation steps. Use as the final step to format findings in a standardized way.
compatibility: Designed for AWS alarm investigation reporting
allowed-tools: []
metadata:
  owner: platform-team
  version: "1.0"
  type: orchestration-only
---

# Investigation Summary Format

## Purpose
Provides the EXACT format and structure for creating comprehensive investigation summaries after completing all AWS alarm investigation steps.

## When to use
- **ALWAYS** use this format after completing all 4 investigation steps
- Use this as the FINAL step in every alarm investigation
- This is MANDATORY - never skip the structured summary
- **NEVER provide generic responses** - always use this structured format

## When not to use
- Before completing the full investigation workflow
- For non-AWS alarm investigations
- When investigation is incomplete or missing critical steps

## Required inputs
- Completed investigation data from all previous steps:
  1. ✅ email-parser results
  2. ✅ log-group-discovery results  
  3. ✅ cloudwatch-fetcher logs
  4. ✅ dependency-checker results

## Workflow
1. Ensure all 4 investigation steps are completed
2. Extract real data from each tool's output
3. Format the summary using the EXACT mandatory structure
4. Provide technical, actionable solutions based on specific errors found

## MANDATORY Summary Format

You MUST use this EXACT format with the emoji and section headers:

```
---
## 🔍 INVESTIGATION SUMMARY

### 1. WHERE IT HAPPENED
[List the specific services and log groups where errors occurred]
- Primary Service: [service name from investigation]
- Primary Log Group: [log group path from log-group-discovery]
- Affected Dependencies: [list any dependencies with errors from dependency-checker]

### 2. WHAT HAPPENED
[Describe the specific error from the actual log messages]
- Error Type: [exact error type from logs]
- Error Message: [actual error message from logs]
- Error Count: [number of occurrences from tool outputs]
- Sample Error: [paste a sample error message from the logs]

### 3. WHY IT HAPPENED (Root Cause)
[Analyze the error to determine the root cause based on actual error messages]
- Root Cause: [specific technical reason based on error analysis]
- Contributing Factors: [any additional factors that contributed]

### 4. POSSIBLE SOLUTIONS
[Provide 2-3 specific, actionable solutions based on the error type]
1. [First solution with technical details]
2. [Second solution with technical details]
3. [Third solution with technical details] (if applicable)
---
```

## Tool usage
This is an orchestration-only skill - no tools are called. Instead:
- Extract data from previous tool outputs
- Format according to the mandatory structure
- Ensure all sections contain real, specific data

## Edge cases
- Missing investigation steps: Note which steps are incomplete
- No errors found: Still use the format but note "No errors detected"
- Validation failures: Include validation status in summary
- Multiple error types: Prioritize the most critical errors

## Output expectations
A properly formatted investigation summary that:
- Uses the exact format with 🔍 emoji and numbered sections
- Contains real data extracted from tool outputs
- Provides specific, actionable technical solutions
- Includes validation results when available

## Quality checklist
Before submitting your summary, verify:
- [ ] Used exact format with 🔍 emoji and 4 numbered sections
- [ ] Extracted real service names from tool outputs
- [ ] Copied actual error messages from logs
- [ ] Identified specific error type (not generic "error")
- [ ] Provided technical, actionable solutions
- [ ] Included validation results if available
- [ ] No made-up or generic information

## Integration with workflow
This skill represents the final step in the investigation workflow:
1. email-parser ← Parse the alert email
2. log-group-discovery ← Find the correct log group
3. cloudwatch-fetcher ← Fetch primary service logs
4. dependency-checker ← Check dependency logs
5. **investigation-summary** ← Format final findings