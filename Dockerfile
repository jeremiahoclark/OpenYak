FROM nvcr.io/nvidia/pytorch:25.08-py3

# ── System deps: Node.js 20 ──────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg zstd && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# ── Ollama ────────────────────────────────────────────────────────────
RUN curl -fsSL https://ollama.com/install.sh | sh

# ── Pre-pull Ollama model into image ──────────────────────────────────
ENV OLLAMA_MODEL=nemotron-3-nano
RUN ollama serve & sleep 3 && ollama pull ${OLLAMA_MODEL} && pkill ollama || true

# ── FLUX server Python deps ──────────────────────────────────────────
RUN python3 -m pip install --no-cache-dir \
    fastapi==0.115.8 \
    uvicorn[standard]==0.30.6 \
    pillow==11.1.0 \
    accelerate==1.3.0 \
    transformers==5.1.0 \
    safetensors==0.5.2 \
    sentencepiece==0.2.0 \
    protobuf==5.29.3 \
    hf-transfer==0.1.9 \
    peft>=0.13.0 \
  && python3 -m pip install --no-cache-dir \
    "git+https://github.com/huggingface/diffusers.git@main"

ENV HF_HUB_ENABLE_HF_TRANSFER=1

# ── Pre-download LoRA weights ────────────────────────────────────────
RUN python3 -c "from huggingface_hub import hf_hub_download; \
    [hf_hub_download('DeverStyle/Flux.2-Klein-Loras', f) for f in [\
        'dever_arcane_flux2_klein_9b.safetensors',\
        'dever_cyanide_and_happiness_flux2_klein_9b.safetensors',\
        'dever_devil_may_cry_flux2_klein_9b.safetensors']]"

WORKDIR /app

# ── Yak Python deps (cached layer) ───────────────────────────────────
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p yak bridge && touch yak/__init__.py && \
    pip install --no-cache-dir . && \
    rm -rf yak bridge

# ── WhatsApp bridge ──────────────────────────────────────────────────
COPY bridge/ bridge/
WORKDIR /app/bridge
RUN npm install && npm run build
WORKDIR /app

# ── Copy FLUX server app ─────────────────────────────────────────────
COPY docker/flux_server/app.py /app/flux_server/app.py

# ── Copy full yak source and install ─────────────────────────────────
COPY yak/ yak/
RUN pip install --no-cache-dir .

# ── Bake .env and config into image ──────────────────────────────────
COPY .env /app/.env
COPY creds/ /app/creds/

# ── Entrypoint ────────────────────────────────────────────────────────
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN mkdir -p /root/.yak

ENV PYTHONUNBUFFERED=1
ENV OLLAMA_HOST=http://127.0.0.1:11434
ENV YAK_IMAGE_BACKEND=flux_server
ENV YAK_FLUX_SERVER_URL=http://127.0.0.1:8010
ENV DATA_ROOT=/app/storage

EXPOSE 18790 8010

ENTRYPOINT ["/app/entrypoint.sh"]
