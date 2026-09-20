#!/bin/bash

set -e

echo "Preparing YouTube cookies..."

cp /etc/secrets/cookies.txt /tmp/cookies.txt
chmod 600 /tmp/cookies.txt

echo "Starting bgutil POT provider..."

(cd bgutil-ytdlp-pot-provider/server && node build/main.js) &

echo "Waiting for bgutil..."

for i in {1..30}; do
    if curl -sS http://127.0.0.1:4416/ping > /dev/null 2>&1; then
        echo "bgutil is ready!"
        break
    fi

    echo "bgutil not ready yet... attempt $i/30"
    sleep 2
done

echo "Starting FastAPI..."

exec uvicorn app:app --host 0.0.0.0 --port "$PORT"