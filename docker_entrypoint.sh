#!/bin/sh
set -e

mkdir -p /data

# Ensure DATABASE_URL points to the persistent data volume
export DATABASE_URL="${DATABASE_URL:-sqlite:////data/bitagent.db}"

exec uvicorn main:app --host 0.0.0.0 --port 8000
