FROM python:3.12-slim

LABEL maintainer="AgentPay Labs <team@agentpay.ai>"
LABEL description="AgentPay Gateway MCP — Centralized API Gateway with Per-Call Billing"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY server.py .
COPY __init__.py .
COPY .env.example .env

# Expose the MCP HTTP port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the gateway server
CMD ["python3", "server.py", "--port", "8000"]