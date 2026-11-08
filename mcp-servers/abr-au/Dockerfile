# One image, three uses (the same volume holds the index):
#   docker run -i --rm -v abr-data:/data IMAGE                        # stdio MCP server (default)
#   docker run --rm -v abr-data:/data IMAGE update-index              # fetch/refresh the index
#   docker run --rm -p 8000:8000 -v abr-data:/data:ro IMAGE serve --http   # streamable-HTTP /mcp
# Add -e ABR_GUID to enable the live ABN Lookup web services.
# Multi-arch: `docker buildx build --platform linux/amd64,linux/arm64 .`
FROM python:3.15-slim

LABEL io.modelcontextprotocol.server.name="io.github.DeepCivic/abr-au" \
      org.opencontainers.image.source="https://github.com/DeepCivic/civic-lab" \
      org.opencontainers.image.description="Unofficial MCP client for ABN Lookup data; not affiliated with or endorsed by the ABR" \
      org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
 && useradd --create-home --uid 10001 abr \
 && mkdir /data && chown abr:abr /data

# The image holds no register data. HOST=0.0.0.0 only matters with --http,
# where the container port is the boundary; publish it deliberately.
ENV ABR_INDEX_PATH=/data/abr.sqlite \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
USER abr
EXPOSE 8000

ENTRYPOINT ["abr-au"]
CMD ["serve"]
