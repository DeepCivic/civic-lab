# Mount the project at /work (read-only is enough), then ask for a review of /work:
#   docker run -i --rm -v "$PWD":/work:ro IMAGE                                          # stdio MCP server (default)
#   docker run --rm -v "$PWD":/work:ro IMAGE review /work --entity-type non_corporate_commonwealth --fail-on blocker
#   docker run --rm -v "$PWD":/work:ro IMAGE verify /work                                # check .ism/controls.yaml, e.g. in CI
#   docker run --rm -p 8000:8000 -v /srv/repos:/work:ro IMAGE serve --http               # streamable-HTTP /mcp
# Everything is offline: the knowledge base ships in the image and no network access is needed.
# Multi-arch: `docker buildx build --platform linux/amd64,linux/arm64 .`
FROM python:3.15-slim

LABEL io.modelcontextprotocol.server.name="io.github.DeepCivic/ism-requirements-au" \
      org.opencontainers.image.source="https://github.com/DeepCivic/civic-lab" \
      org.opencontainers.image.description="Derive and track Australian Government ISM requirements for a system. Decision support, not an IRAP assessment." \
      org.opencontainers.image.licenses="Apache-2.0"

# git lets the scanner honour .gitignore in mounted repositories (mounted files belong to another user).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*'

WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN pip install --no-cache-dir . \
 && useradd --create-home --uid 10001 reviewer \
 && mkdir /work

# The MCP server may read only /work (ISM_REQUIREMENTS_AU_ROOTS); the CLI reads whatever path you give it.
# HOST=0.0.0.0 only matters with --http, where the container port is the boundary; publish it deliberately.
ENV ISM_REQUIREMENTS_AU_ROOTS=/work \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1
USER reviewer
WORKDIR /work
EXPOSE 8000

ENTRYPOINT ["ism-requirements-au"]
CMD ["serve"]
