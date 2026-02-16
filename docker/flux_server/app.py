from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ── LoRA style registry ──────────────────────────────────────────────
LORA_STYLES: dict[str, dict[str, str]] = {
    "arcane": {
        "repo": "DeverStyle/Flux.2-Klein-Loras",
        "file": "dever_arcane_flux2_klein_9b.safetensors",
        "trigger": "arcane_visual_style",
    },
    "cyanide_and_happiness": {
        "repo": "DeverStyle/Flux.2-Klein-Loras",
        "file": "dever_cyanide_and_happiness_flux2_klein_9b.safetensors",
        "trigger": "ch_visual_style, stick figure character",
    },
    "devil_may_cry": {
        "repo": "DeverStyle/Flux.2-Klein-Loras",
        "file": "dever_devil_may_cry_flux2_klein_9b.safetensors",
        "trigger": "dmc_style",
    },
}

AVAILABLE_STYLES = list(LORA_STYLES.keys())


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1)
    width: int = Field(default=768, ge=256, le=1536)
    height: int = Field(default=768, ge=256, le=1536)
    steps: int = Field(default=4, ge=1, le=20)
    seed: int = Field(default=7, ge=0)
    guidance_scale: float = Field(default=1.0, ge=0.1, le=10.0)
    style: str | None = Field(
        default=None,
        description=f"LoRA style to apply. Available: {AVAILABLE_STYLES}",
    )
    output_relpath: str = Field(
        description="Path relative to DATA_ROOT where the PNG will be written.",
        min_length=1,
    )


class GenerateImageResponse(BaseModel):
    status: Literal["ok"]
    output_path: str
    model_id: str
    style: str | None = None


DATA_ROOT = Path(os.getenv("DATA_ROOT", "/data")).resolve()
MODEL_ID = os.getenv("FLUX_MODEL_ID", "black-forest-labs/FLUX.2-klein-9B").strip()

_pipe = None
_current_lora: str | None = None  # tracks which LoRA is loaded


def _load_pipe():
    global _pipe
    if _pipe is not None:
        return _pipe

    try:
        from diffusers import Flux2KleinPipeline
    except Exception as exc:
        raise RuntimeError("diffusers Flux2KleinPipeline not available") from exc

    pipe = Flux2KleinPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for FLUX.2-klein service")
    pipe.to("cuda")
    _pipe = pipe
    return pipe


def _apply_lora(pipe, style: str | None) -> None:
    """Load / swap / unload LoRA weights as needed."""
    global _current_lora

    if style == _current_lora:
        return  # already loaded (or both None)

    # Unload previous LoRA if any
    if _current_lora is not None:
        try:
            pipe.unload_lora_weights()
        except Exception:
            pass
        _current_lora = None

    # Load new LoRA if requested
    if style is not None:
        info = LORA_STYLES.get(style)
        if not info:
            raise ValueError(f"Unknown style '{style}'. Available: {AVAILABLE_STYLES}")
        pipe.load_lora_weights(info["repo"], weight_name=info["file"])
        _current_lora = style


def _safe_output_path(output_relpath: str) -> Path:
    rel = Path(output_relpath)
    if rel.is_absolute():
        raise ValueError("output_relpath must be relative")
    out = (DATA_ROOT / rel).resolve()
    if DATA_ROOT not in out.parents and out != DATA_ROOT:
        raise ValueError("output path escapes DATA_ROOT")
    return out


app = FastAPI(title="Yak FLUX Image Service", version="0.2.0")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/styles")
def list_styles():
    """List available LoRA styles."""
    return {
        "styles": {
            name: {"trigger": info["trigger"], "file": info["file"]}
            for name, info in LORA_STYLES.items()
        }
    }


@app.post("/generate_image", response_model=GenerateImageResponse)
def generate_image(req: GenerateImageRequest):
    try:
        out = _safe_output_path(req.output_relpath)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Klein distilled models require fixed num_steps/guidance.
    steps = 4
    guidance_scale = 1.0

    # Validate style if provided
    style = req.style.strip().lower() if req.style else None
    if style and style not in LORA_STYLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown style '{style}'. Available: {AVAILABLE_STYLES}",
        )

    try:
        pipe = _load_pipe()

        # Apply or swap LoRA
        _apply_lora(pipe, style)

        # Prepend trigger word if using a style
        prompt = req.prompt
        if style:
            trigger = LORA_STYLES[style]["trigger"]
            if trigger.lower() not in prompt.lower():
                prompt = f"{trigger}, {prompt}"

        gen = torch.Generator(device="cuda").manual_seed(int(req.seed))
        with torch.inference_mode():
            result = pipe(
                prompt=prompt,
                width=int(req.width),
                height=int(req.height),
                num_inference_steps=int(steps),
                guidance_scale=float(guidance_scale),
                generator=gen,
            )
        img = result.images[0]
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
        return GenerateImageResponse(
            status="ok", output_path=str(out), model_id=MODEL_ID, style=style
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e
