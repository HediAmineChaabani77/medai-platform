#!/usr/bin/env bash
# Persist ollama serve across wsl command invocations.
pkill -f "ollama serve" 2>/dev/null || true
sleep 1
nohup env OLLAMA_HOST=0.0.0.0:11436 OLLAMA_NUM_PARALLEL=4 OLLAMA_KEEP_ALIVE=60m \
  "$HOME/ollama/extracted/bin/ollama" serve \
  > /tmp/ollama.log 2>&1 < /dev/null &
disown
echo "launched pid=$!"
# Wait up to 30s for readiness
for i in $(seq 1 30); do
  if curl -sf http://localhost:11436/api/tags >/dev/null 2>&1; then
    echo "ready after ${i}s"
    curl -s http://localhost:11436/api/tags | head -c 200
    exit 0
  fi
  sleep 1
done
echo "not ready"
exit 1
