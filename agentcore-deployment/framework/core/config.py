"""
Config loader for AgentCore deployment.

Loads configuration from environment variables instead of config.yaml.
Credentials are securely stored in AWS Systems Manager Parameter Store.
"""

import os
import json
import boto3
from typing import Any, Dict

import logging
logger = logging.getLogger(__name__)


def get_parameter(parameter_name: str, region: str = "ap-south-1") -> Dict[str, Any]:
    """
    Retrieve parameter from AWS Systems Manager Parameter Store.
    
    Args:
        parameter_name: Name of the parameter in Parameter Store
        region: AWS region
        
    Returns:
        Parsed parameter as dictionary (if JSON) or string
    """
    try:
        client = boto3.client('ssm', region_name=region)
        response = client.get_parameter(Name=parameter_name, WithDecryption=True)
        value = response['Parameter']['Value']
        
        # Try to parse as JSON, otherwise return as string
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
    except Exception as e:
        logger.error(f"Failed to retrieve parameter {parameter_name}: {e}")
        raise



class Config:
    """Load configuration from environment variables for Lambda deployment."""

    def __init__(self):
        """Initialize config from environment variables."""
        self._load_from_env()

    @classmethod
    def from_env(cls) -> 'Config':
        """Factory method to create Config from environment."""
        return cls()

    def _load_from_env(self):
        """Load all configuration from environment variables."""
        # AWS Region
        self._aws_region = os.environ.get('AWS_REGION', 'ap-south-1')
        
        # Bedrock configuration
        self._bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', 'apac.amazon.nova-lite-v1:0')
        self._bedrock_region = os.environ.get('BEDROCK_REGION', self._aws_region)
        
        # Parameter Store paths
        graph_param_name = os.environ.get('GRAPH_API_SECRET_NAME')
        teams_param_name = os.environ.get('TEAMS_WEBHOOK_SECRET_NAME')
        cloudwatch_param_name = os.environ.get('CLOUDWATCH_CREDENTIALS_NAME')
        
        # Email/Graph API configuration
        if graph_param_name:
            try:
                logger.info(f"Loading Graph API credentials from Parameter Store: {graph_param_name}")
                graph_data = get_parameter(graph_param_name, self._aws_region)
                
                self._email_config = {
                    'tenantId': graph_data.get('tenantId'),
                    'clientId': graph_data.get('clientId'),
                    'clientSecret': graph_data.get('clientSecret'),
                    'userId': graph_data.get('userId'),
                    'poll_interval': int(os.environ.get('EMAIL_POLL_INTERVAL', '60')),
                    'subject_filter': os.environ.get('EMAIL_SUBJECT_FILTER', 'ALARM'),
                }
                logger.info("Graph API credentials loaded successfully")
            except Exception as e:
                logger.error(f"Could not load Graph API credentials from Parameter Store: {e}")
                self._email_config = {}
        else:
            # Fallback to direct environment variables
            logger.info("Using direct environment variables for Graph API credentials")
            self._email_config = {
                'tenantId': os.environ.get('GRAPH_TENANT_ID'),
                'clientId': os.environ.get('GRAPH_CLIENT_ID'),
                'clientSecret': os.environ.get('GRAPH_CLIENT_SECRET'),
                'userId': os.environ.get('GRAPH_USER_ID'),
                'poll_interval': int(os.environ.get('EMAIL_POLL_INTERVAL', '60')),
                'subject_filter': os.environ.get('EMAIL_SUBJECT_FILTER', 'ALARM'),
            }
        
        # Teams configuration
        if teams_param_name:
            try:
                logger.info(f"Loading Teams webhook from Parameter Store: {teams_param_name}")
                teams_data = get_parameter(teams_param_name, self._aws_region)
                
                self._teams_config = {
                    'webhook_url': teams_data.get('webhook_url'),
                    'enabled': os.environ.get('TEAMS_ENABLED', 'true').lower() == 'true',
                }
                logger.info("Teams webhook loaded successfully")
            except Exception as e:
                logger.error(f"Could not load Teams webhook from Parameter Store: {e}")
                self._teams_config = {'enabled': False}
        else:
            # Fallback to direct environment variable
            logger.info("Using direct environment variable for Teams webhook")
            self._teams_config = {
                'webhook_url': os.environ.get('TEAMS_WEBHOOK_URL'),
                'enabled': os.environ.get('TEAMS_ENABLED', 'true').lower() == 'true',
            }
        
        # CloudWatch cross-account credentials (for reading logs from different AWS account)
        if cloudwatch_param_name:
            try:
                logger.info(f"Loading CloudWatch cross-account credentials from Parameter Store: {cloudwatch_param_name}")
                cw_data = get_parameter(cloudwatch_param_name, self._aws_region)
                
                self._cloudwatch_config = {
                    'access_key_id': cw_data.get('access_key_id'),
                    'secret_access_key': cw_data.get('secret_access_key'),
                    'region': cw_data.get('region', self._aws_region)
                }
                logger.info("CloudWatch cross-account credentials loaded successfully")
            except Exception as e:
                logger.error(f"Could not load CloudWatch credentials from Parameter Store: {e}")
                self._cloudwatch_config = {}
        else:
            # No cross-account credentials - will use Lambda execution role
            logger.info("No cross-account CloudWatch credentials configured - using Lambda execution role")
            self._cloudwatch_config = {}
        
        # AWS configuration (uses Lambda execution role by default)
        self._aws_config = {
            'region': self._aws_region,
        }
        
        # Agent configuration
        self._agent_config = {
            'max_iterations': int(os.environ.get('AGENT_MAX_ITERATIONS', '70')),
            'memory_file': os.environ.get('MEMORY_FILE', 'memory.json'),
            'verbose': os.environ.get('AGENT_VERBOSE', 'true').lower() == 'true',
            'services_registry': os.environ.get('SERVICES_REGISTRY_PATH', 'services.yaml'),
        }
        
        logger.info(f"Agent config: max_iterations={self._agent_config['max_iterations']}, verbose={self._agent_config['verbose']}")
        
        logger.info(f"Config loaded: model={self._bedrock_model_id}, region={self._bedrock_region}")

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Access nested config via dot notation (for compatibility)."""
        keys = dotted_key.split(".")
        
        # Map dotted keys to attributes
        config_map = {
            'bedrock': {
                'model_id': self._bedrock_model_id,
                'region': self._bedrock_region,
            },
            'email': self._email_config,
            'aws': self._aws_config,
            'teams': self._teams_config,
            'agent': self._agent_config,
            'cloudwatch': self._cloudwatch_config,
        }
        
        value = config_map
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    # ── Convenience properties ─────────────────────────────────────────

    @property
    def bedrock_model_id(self) -> str:
        return self._bedrock_model_id

    @property
    def bedrock_region(self) -> str:
        return self._bedrock_region

    @property
    def bedrock_access_key_id(self) -> str:
        # Lambda uses execution role, no explicit credentials needed
        return ""

    @property
    def bedrock_secret_access_key(self) -> str:
        # Lambda uses execution role, no explicit credentials needed
        return ""

    @property
    def bedrock_session_token(self) -> str:
        # Lambda uses execution role, no explicit credentials needed
        return ""

    @property
    def email_config(self) -> dict:
        return self._email_config

    @property
    def aws_config(self) -> dict:
        return self._aws_config

    @property
    def log_groups(self) -> dict:
        # Not used in Lambda deployment (dynamic discovery)
        return {}

    @property
    def agent_config(self) -> dict:
        return self._agent_config

    @property
    def services_registry_path(self) -> str:
        """Get path to services.yaml."""
        return self._agent_config.get('services_registry', 'services.yaml')

    @property
    def teams_config(self) -> dict:
        return self._teams_config

    @property
    def cloudwatch_config(self) -> dict:
        return self._cloudwatch_config
