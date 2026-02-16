#!/usr/bin/env bash
set -euo pipefail

# ── Load baked .env if present ────────────────────────────────────────
if [ -f /app/.env ]; then
    set -a; source /app/.env; set +a
fi

# ── Ensure ~/.yak/config.json exists ─────────────────────────────────
if [ ! -f /root/.yak/config.json ]; then
    mkdir -p /root/.yak
    yak onboard 2>/dev/null || true
fi

# ── Graceful shutdown ─────────────────────────────────────────────────
PIDS=()

cleanup() {
    echo "[entrypoint] Shutting down…"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait
    echo "[entrypoint] All processes stopped."
    exit 0
}
trap cleanup SIGTERM SIGINT

# ── 1. Ollama ─────────────────────────────────────────────────────────
echo "[entrypoint] Starting Ollama…"
ollama serve &
PIDS+=($!)

# Wait for Ollama to be ready
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "[entrypoint] Ollama is ready."
        break
    fi
    sleep 1
done

# Pull configured model only if not already present
MODEL="${OLLAMA_MODEL:-}"
if [ -n "$MODEL" ]; then
    if ollama list 2>/dev/null | grep -q "^${MODEL}"; then
        echo "[entrypoint] Model '${MODEL}' already present, skipping pull."
    else
        echo "[entrypoint] Pulling Ollama model: $MODEL"
        ollama pull "$MODEL" || echo "[entrypoint] WARNING: Failed to pull $MODEL"
    fi
fi

# ── 2. FLUX image server ─────────────────────────────────────────────
echo "[entrypoint] Starting FLUX server on :8010…"
python3 -m uvicorn flux_server.app:app \
    --host 0.0.0.0 --port 8010 \
    --app-dir /app &
PIDS+=($!)

# ── 3. Yak gateway (foreground) ──────────────────────────────────────
echo "[entrypoint] Starting yak gateway on :18790…"
exec yak gateway
