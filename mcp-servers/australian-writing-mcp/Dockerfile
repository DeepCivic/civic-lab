# AWS Bedrock AgentCore Runtime requires linux/arm64.
FROM --platform=linux/arm64 python:3.11-slim

WORKDIR /app

# Install the package (pure-Python deps; the en_AU dictionary is bundled).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# AgentCore expects the MCP server on 0.0.0.0:8000/mcp.
EXPOSE 8000

# Serve streamable-HTTP, stateless, on /mcp (see australian_writing.server.main).
CMD ["python", "-m", "australian_writing.server", "--http"]
