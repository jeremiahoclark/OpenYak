FROM nvcr.io/nvidia/pytorch:25.08-py3

WORKDIR /app

# Keep installs reproducible-ish; diffusers is pinned to a git ref that matches our current needs
# (Flux2KleinPipeline exists on diffusers main as of 2026-02). If this breaks, pin to a commit.
RUN python3 -m pip install --upgrade pip \
  && python3 -m pip install --no-cache-dir \
    fastapi==0.115.8 \
    uvicorn[standard]==0.30.6 \
    pydantic==2.10.6 \
    pillow==11.1.0 \
    accelerate==1.3.0 \
    transformers==5.1.0 \
    safetensors==0.5.2 \
    sentencepiece==0.2.0 \
    protobuf==5.29.3 \
    hf-transfer==0.1.9 \
  && python3 -m pip install --no-cache-dir \
    "git+https://github.com/huggingface/diffusers.git@main"

ENV HF_HUB_ENABLE_HF_TRANSFER=1
ENV PYTHONUNBUFFERED=1

COPY app.py /app/app.py

EXPOSE 8010

CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]
