#!/bin/sh
set -e

cd /app

if [ "$#" -gt 0 ]; then
    if [ "$1" = "rq" ]; then
        REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"
        echo "Waiting for Redis at $REDIS_URL..."
        python - <<'PY'
import os
import time
from redis import Redis

url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
while True:
    try:
        Redis.from_url(url).ping()
        print('Redis reachable:', url)
        break
    except Exception as exc:
        print('Redis unavailable:', exc)
        time.sleep(2)
PY
    fi
    exec "$@"
fi

exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-2}"
