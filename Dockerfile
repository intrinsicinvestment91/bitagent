FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    BITAGENT_DATA_DIR=/data

WORKDIR /app

# git is needed to install the python-nostr VCS dependency; curl for HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*

COPY . .

COPY docker_entrypoint.sh /usr/local/bin/docker_entrypoint.sh
RUN chmod +x /usr/local/bin/docker_entrypoint.sh

# The payment ledger and identity database live here. Mount a volume at /data in
# production: losing the ledger would make every past payment replayable.
RUN mkdir -p /data \
    && useradd --create-home --uid 10001 bitagent \
    && chown -R bitagent:bitagent /app /data
USER bitagent

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# The image previously declared no CMD at all, so it could not be run without an
# external start command. Railway's startCommand still overrides this.
ENTRYPOINT ["/usr/local/bin/docker_entrypoint.sh"]
