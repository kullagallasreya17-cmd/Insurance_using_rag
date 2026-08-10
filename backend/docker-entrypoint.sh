#!/bin/sh
set -e

cd /app

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-2}"
