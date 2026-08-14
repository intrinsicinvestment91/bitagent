#!/bin/sh
set -e

# The payment ledger and identity store live here. In production this must be a
# mounted volume: if the ledger is lost, every previously settled payment hash
# becomes replayable.
DATA_DIR="${BITAGENT_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

exec uvicorn main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --proxy-headers \
    --forwarded-allow-ips '*'
