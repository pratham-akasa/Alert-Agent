FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

# All environment variables in one layer
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    AWS_REGION=ap-south-1 \
    AWS_DEFAULT_REGION=ap-south-1 \
    BEDROCK_MODEL_ID=apac.amazon.nova-lite-v1:0 \
    BEDROCK_REGION=ap-south-1 \
    GRAPH_API_SECRET_NAME=/rca-alert-bot/graph-api \
    TEAMS_WEBHOOK_SECRET_NAME=/rca-alert-bot/teams/webhook-url \
    CLOUDWATCH_CREDENTIALS_NAME=/rca-alert-bot/cloudwatch-credentials \
    MEMORY_BUCKET=aws-alert-bot-memory \
    MEMORY_BUCKET_ARN=arn:aws:s3:::aws-alert-bot-memory \
    MEMORY_KEY=memory.json \
    AGENT_MAX_ITERATIONS=70 \
    AGENT_VERBOSE=true

COPY requirements.txt requirements.txt
# Install from requirements file
RUN uv pip install -r requirements.txt

RUN uv pip install aws-opentelemetry-distro==0.12.2

# Signal that this is running in Docker for host binding logic
ENV DOCKER_CONTAINER=1

# Create non-root user
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 9000
EXPOSE 8000
EXPOSE 8080

# Copy entire project (respecting .dockerignore)
COPY . .

# Use the full module path

CMD ["opentelemetry-instrument", "python", "-m", "lambda_handler"]
