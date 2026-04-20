#!/usr/bin/env bash
# Launch Ollama on the WSL host (not in Docker) so GTX 1650 GPU passthrough works
# without needing nvidia-container-toolkit. The backend container reaches it
# via host.docker.internal:11436 (set in docker-compose.yml).
set -e

BIN=$HOME/ollama/extracted/bin/ollama
[ -x "$BIN" ] || { echo "Ollama binary not found at $BIN"; exit 1; }

export OLLAMA_HOST=0.0.0.0:11436

# Kill any existing ollama serve on 11436
pkill -f "ollama serve" 2>/dev/null || true
sleep 1

nohup "$BIN" serve > /tmp/ollama.log 2>&1 &
echo "ollama serve pid=$!"

for i in $(seq 1 30); do
  if curl -sfS http://localhost:11436/api/tags >/dev/null 2>&1; then
    echo "ollama is up on :11436 after ${i}s"
    "$BIN" list
    exit 0
  fi
  sleep 1
done
echo "ollama failed to come up; see /tmp/ollama.log"
exit 1
