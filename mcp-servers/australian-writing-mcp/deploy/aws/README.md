# Deploy to AWS Bedrock AgentCore Runtime

AgentCore Runtime is AWS's managed host for MCP servers. This server already
meets its protocol contract:

| AgentCore requirement | How this server satisfies it |
| --- | --- |
| Streamable-HTTP transport | `--http` runs `mcp.run(transport="streamable-http")` |
| Stateless mode | `stateless_http=True` is set in HTTP mode |
| Listen on `0.0.0.0:8000` | FastMCP defaults (overridable via `HOST`/`PORT`) |
| `POST /mcp` endpoint | FastMCP's default streamable path is `/mcp` |
| `application/json` + `text/event-stream` | handled by FastMCP |
| Accept the platform `Mcp-Session-Id` header | handled by FastMCP |
| **linux/arm64** container | `Dockerfile` pins `--platform=linux/arm64` |

Verify locally first:

```bash
python -m australian_writing.server --http        # serves http://0.0.0.0:8000/mcp
```

## Option A — starter toolkit (recommended)

The toolkit builds the ARM64 image (via CodeBuild), pushes to ECR, creates the
IAM role, and registers the runtime.

```bash
pip install bedrock-agentcore-starter-toolkit
agentcore configure --entrypoint src/australian_writing/server.py --protocol MCP
agentcore launch
```

## Option B — manual (Docker + ECR + CLI)

```bash
ACCOUNT=123456789012; REGION=ap-southeast-2; REPO=australian-writing-mcp

# 1. Build ARM64 image and push to ECR
aws ecr create-repository --repository-name $REPO --region $REGION
aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
docker buildx build --platform linux/arm64 \
  -t $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest --push .

# 2. Create the execution role (trust policy in trust-policy.json)
aws iam create-role --role-name AgentCoreAusWritingExec \
  --assume-role-policy-document file://deploy/aws/trust-policy.json
# Attach permissions for ECR pull + CloudWatch logs (scope down for production).

# 3. Register the MCP runtime
aws bedrock-agentcore-control create-agent-runtime \
  --agent-runtime-name australian_writing \
  --agent-runtime-artifact '{"containerConfiguration":{"containerUri":"'$ACCOUNT'.dkr.ecr.'$REGION'.amazonaws.com/'$REPO':latest"}}' \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --protocol-configuration '{"serverProtocol":"MCP"}' \
  --role-arn arn:aws:iam::$ACCOUNT:role/AgentCoreAusWritingExec \
  --region $REGION
```

## Authentication

Unlike stdio (trusted-local), a hosted endpoint needs inbound auth. AgentCore
supports **IAM (SigV4)** by default, or **JWT/OAuth** via AgentCore Identity
(e.g. an Amazon Cognito user pool). Configure this on the runtime; clients then
present a bearer token or signed request to reach `/mcp`.

> The app itself needs no secrets, database, or environment configuration — the
> only setup is this container/runtime contract plus the auth layer.

Commands use placeholder account/region/role names; check the current AWS docs
for the latest `create-agent-runtime` parameters.
