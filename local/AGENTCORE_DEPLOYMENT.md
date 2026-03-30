# AWS Bedrock AgentCore Deployment Guide

Complete step-by-step guide to deploy the AWS Alert Bot to Amazon Bedrock AgentCore.

## Prerequisites

1. **AWS Account** with permissions for:
   - Bedrock AgentCore
   - IAM (create roles)
   - Secrets Manager
   - CloudWatch Logs
   - Resource Explorer

2. **AWS CLI** configured:
   ```bash
   aws configure
   ```

3. **Python 3.11+** installed

4. **Bedrock AgentCore CLI** installed:
   ```bash
   pip install bedrock-agentcore-cli
   ```

## Step-by-Step Deployment

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- LangChain + LangGraph
- AWS SDK (boto3)
- Bedrock AgentCore SDK
- All other dependencies

### Step 2: Store Secrets in AWS Secrets Manager

Your agent needs credentials for Microsoft Graph API and Teams. Store them securely:

#### Create Graph API Secret

```bash
aws secretsmanager create-secret \
  --name aws-alert-bot/graph-api \
  --region ap-south-1 \
  --secret-string '{
    "tenantId": "YOUR_TENANT_ID",
    "clientId": "YOUR_CLIENT_ID",
    "clientSecret": "YOUR_CLIENT_SECRET",
    "userId": "internal.automations@akasaair.com"
  }'
```

#### Create Teams Webhook Secret

```bash
aws secretsmanager create-secret \
  --name aws-alert-bot/teams-webhook \
  --region ap-south-1 \
  --secret-string '{
    "webhook_url": "YOUR_TEAMS_WEBHOOK_URL"
  }'
```

**Windows PowerShell:**
```powershell
aws secretsmanager create-secret `
  --name aws-alert-bot/graph-api `
  --region ap-south-1 `
  --secret-string '{"tenantId":"YOUR_TENANT_ID","clientId":"YOUR_CLIENT_ID","clientSecret":"YOUR_CLIENT_SECRET","userId":"internal.automations@akasaair.com"}'
```

### Step 3: Update config.yaml to Use Secrets

Your `config.yaml` should reference secrets instead of hardcoded credentials:

```yaml
bedrock:
  model_id: "apac.amazon.nova-lite-v1:0"
  region: "ap-south-1"
  # Credentials will be auto-loaded from IAM role

email:
  # Will be loaded from Secrets Manager
  secret_name: "aws-alert-bot/graph-api"
  poll_interval: 60
  subject_filter: "ALARM"

aws:
  # Credentials will be auto-loaded from IAM role
  region: ap-south-1

teams:
  # Will be loaded from Secrets Manager
  secret_name: "aws-alert-bot/teams-webhook"
  enabled: true

agent:
  max_iterations: 10
  memory_file: "memory.json"
  verbose: true
```

### Step 4: Deploy to AgentCore

#### Option A: Using Deployment Script (Recommended)

**Linux/Mac:**
```bash
chmod +x deploy_agentcore.sh
./deploy_agentcore.sh
```

**Windows:**
```powershell
.\deploy_agentcore.ps1
```

#### Option B: Manual Deployment

```bash
agentcore deploy \
  --config agentcore_config.yaml \
  --region ap-south-1 \
  --yes
```

### Step 5: Verify Deployment

Check agent status:
```bash
agentcore describe --name aws-alert-bot --region ap-south-1
```

Expected output:
```json
{
  "agentName": "aws-alert-bot",
  "agentArn": "arn:aws:bedrock:ap-south-1:ACCOUNT_ID:agent/aws-alert-bot",
  "status": "ACTIVE",
  "runtime": "python3.11",
  "memory": 2048,
  "timeout": 600
}
```

### Step 6: Test the Agent

#### Test with a simple prompt:
```bash
agentcore invoke \
  --name aws-alert-bot \
  --region ap-south-1 \
  --payload '{"prompt": "Test investigation"}'
```

#### Test with a sample alarm event:
```bash
agentcore invoke \
  --name aws-alert-bot \
  --region ap-south-1 \
  --payload '{
    "event": {
      "source": "email",
      "event_type": "aws_alarm",
      "payload": {
        "subject": "ALARM: test-alarm",
        "from": "no-reply@sns.amazonaws.com",
        "body": "Test alarm body"
      }
    }
  }'
```

### Step 7: Monitor the Agent

#### View real-time logs:
```bash
agentcore logs --name aws-alert-bot --follow
```

#### View CloudWatch metrics:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/BedrockAgentCore \
  --metric-name Invocations \
  --dimensions Name=AgentName,Value=aws-alert-bot \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

#### View CloudWatch Logs:
```bash
aws logs tail /aws/bedrock/agentcore/aws-alert-bot --follow
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  EventBridge Schedule                   │
│              (triggers every 1 minute)                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│              AWS Bedrock AgentCore                      │
│                                                         │
│  ┌───────────────────────────────────────────────┐     │
│  │         agentcore_runtime.py                  │     │
│  │  (handles invocations, manages agent)         │     │
│  └───────────────────┬───────────────────────────┘     │
│                      │                                  │
│                      ↓                                  │
│  ┌───────────────────────────────────────────────┐     │
│  │         framework/core/agent.py               │     │
│  │  (LangGraph ReAct agent + tools)              │     │
│  └───────────────────┬───────────────────────────┘     │
│                      │                                  │
│                      ↓                                  │
│  ┌───────────────────────────────────────────────┐     │
│  │              Tool Execution                   │     │
│  │  • parse_aws_alert_email                      │     │
│  │  • discover_log_group                         │     │
│  │  • fetch_cloudwatch_logs                      │     │
│  │  • check_service_dependencies                 │     │
│  │  • notify_teams                               │     │
│  └───────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│              External Services                          │
│  • Microsoft Graph API (email polling)                  │
│  • AWS CloudWatch Logs                                  │
│  • AWS Resource Explorer                                │
│  • Microsoft Teams (notifications)                      │
└─────────────────────────────────────────────────────────┘
```

## Cost Estimation

### AgentCore Costs
- **Compute**: ~$0.10 per hour of execution time
- **Memory**: 2GB @ $0.0000166667 per GB-second
- **Invocations**: 60 per hour (1/minute) = ~1,440/day

### Bedrock Costs (Nova Lite)
- **Input tokens**: ~$0.00006 per 1K tokens
- **Output tokens**: ~$0.00024 per 1K tokens
- **Estimated**: ~$5-10/day for moderate alarm volume

### Total Estimated Cost
- **~$150-300/month** for continuous operation

## Troubleshooting

### Issue: "Agent not found"
```bash
# Check if agent exists
agentcore list --region ap-south-1
```

### Issue: "Permission denied"
```bash
# Check IAM role permissions
aws iam get-role --role-name BedrockAgentCoreExecutionRole-aws-alert-bot
```

### Issue: "Secrets not accessible"
```bash
# Test secret access
aws secretsmanager get-secret-value --secret-id aws-alert-bot/graph-api
```

### Issue: "Agent timeout"
- Increase timeout in `agentcore_config.yaml` (currently 600s)
- Check CloudWatch Logs for slow tool execution

### Issue: "Memory errors"
- Increase memory in `agentcore_config.yaml` (currently 2048MB)

## Updating the Agent

After making code changes:

```bash
# Redeploy
agentcore deploy --config agentcore_config.yaml --region ap-south-1 --yes

# Or use the script
./deploy_agentcore.sh
```

## Deleting the Agent

```bash
agentcore delete --name aws-alert-bot --region ap-south-1 --yes
```

## Next Steps

1. **Set up monitoring alerts** for agent failures
2. **Configure auto-scaling** based on alarm volume
3. **Add custom metrics** for investigation success rate
4. **Implement memory persistence** using S3 or DynamoDB
5. **Add integration tests** for AgentCore deployment

## Support

For issues or questions:
- Check CloudWatch Logs: `/aws/bedrock/agentcore/aws-alert-bot`
- Review AgentCore documentation: https://docs.aws.amazon.com/bedrock/agentcore
- Check agent status: `agentcore describe --name aws-alert-bot`
