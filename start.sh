echo "Starting bgutil POT provider..."
(cd bgutil-ytdlp-pot-provider/server && node build/main.js) &

sleep 5

echo "Checking bgutil..."
curl -sS http://127.0.0.1:4416/ping || true

echo "Starting FastAPI..."
exec uvicorn app:app --host 0.0.0.0 --port "$PORT"