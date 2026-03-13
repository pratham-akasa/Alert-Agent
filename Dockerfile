# Use Python 3.9 slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY framework/ ./framework/
COPY main.py .
COPY config.yaml .
COPY services.yaml .

# Create logs directory
RUN mkdir -p logs

# Create a non-root user
RUN useradd -m -u 1000 alertbot && \
    chown -R alertbot:alertbot /app

USER alertbot

# Default command (can be overridden)
CMD ["python", "main.py"]
