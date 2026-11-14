# One image, three uses (the same volume holds the snapshots):
#   docker run --rm -v sanctions-data:/data IMAGE refresh              # fetch/refresh the data (needs network)
#   docker run -i --rm -v sanctions-data:/data:ro IMAGE                # stdio MCP server (default), no network needed
#   docker run --rm -p 8000:8000 -v sanctions-data:/data:ro IMAGE serve --http
# Air-gapped: refresh somewhere with network, then move the volume (or SANCTIONS_DATA_DIR) across.
FROM python:3.15-slim

LABEL io.modelcontextprotocol.server.name="io.github.DeepCivic/sanctions-au" \
      org.opencontainers.image.source="https://github.com/DeepCivic/civic-lab" \
      org.opencontainers.image.description="Unofficial MCP server for screening against DFAT and ABF sanctions data; not affiliated with or endorsed by either" \
      org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
 && useradd --create-home --uid 10001 sanctions \
 && mkdir /data && chown sanctions:sanctions /data

# The image holds no list data. HOST=0.0.0.0 only matters with --http, where the container
# port is the boundary; publish it deliberately.
ENV SANCTIONS_DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
USER sanctions
EXPOSE 8000

ENTRYPOINT ["sanctions-au"]
CMD ["serve"]
