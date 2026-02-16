"""Text -> image -> video workflow for Yak."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from yak.config.env import load_runtime_env


class WorkflowError(RuntimeError):
    """Raised when workflow execution fails."""


@dataclass
class WorkflowResult:
    image_path: str
    video_path: str
    request_id: str
    remote_url: str
    image_model: str
    video_model: str


class TextToVideoWorkflow:
    """Run local image generation followed by Fal image-to-video."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        fal_api_key: str | None = None,
        image_model_id: str = "black-forest-labs/FLUX.2-klein-9B",
        fal_image_model: str = "fal-ai/kling-video/v3/pro/image-to-video",
        fal_queue_base: str = "https://queue.fal.run",
        poll_interval_seconds: float = 2.0,
        poll_timeout_seconds: float = 900.0,
        image_timeout_seconds: float = 600.0,
    ):
        load_runtime_env()
        self.project_root = (project_root or self._discover_project_root()).resolve()
        self.storage_root = self.project_root / "storage" / "workflows"
        self.storage_root.mkdir(parents=True, exist_ok=True)

        self.fal_api_key = (fal_api_key or os.getenv("FAL_KEY", "")).strip()
        self.image_model_id = image_model_id
        self.fal_image_model = fal_image_model
        self.fal_queue_base = fal_queue_base.rstrip("/")
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.image_timeout_seconds = image_timeout_seconds

        self._flux_pipe: Any | None = None
        self._fal_request_urls: dict[str, dict[str, str]] = {}

    @staticmethod
    def _flux_placement_mode() -> str:
        return os.getenv("YAK_FLUX_PLACEMENT", "cuda").strip().lower()

    @staticmethod
    def _image_backend() -> str:
        return os.getenv("YAK_IMAGE_BACKEND", "flux2_cli").strip().lower()

    @staticmethod
    def _flux_server_url() -> str:
        return os.getenv("YAK_FLUX_SERVER_URL", "http://127.0.0.1:8010").strip().rstrip("/")

    def _discover_project_root(self) -> Path:
        here = Path(__file__).resolve()
        for parent in [here] + list(here.parents):
            if (parent / "pyproject.toml").exists():
                return parent
        return Path.cwd()

    def _discover_flux2_repo(self) -> Path:
        configured = os.getenv("YAK_FLUX2_REPO", "").strip()
        if configured:
            repo = Path(configured).expanduser().resolve()
        else:
            repo = (self.project_root.parent / "flux2").resolve()
        if not repo.exists():
            raise WorkflowError(
                f"FLUX2 repo not found at {repo}. Set YAK_FLUX2_REPO to the official clone path."
            )
        cli = repo / "scripts" / "cli.py"
        if not cli.exists():
            raise WorkflowError(f"FLUX2 CLI not found at {cli}")
        return repo

    def _workflow_dir(self, user_id: str, session_id: str) -> Path:
        session_safe = session_id.replace(":", "_").replace("/", "_")
        out = self.storage_root / user_id / session_safe
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _build_image_path(self, user_id: str, session_id: str) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return self._workflow_dir(user_id, session_id) / f"{ts}_workflow_image.png"

    def _build_video_path(self, user_id: str, session_id: str) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return self._workflow_dir(user_id, session_id) / f"{ts}_workflow_video.mp4"

    @staticmethod
    def _supports_cuda_capability(torch_module: Any, capability: tuple[int, int]) -> bool:
        arch = f"sm_{capability[0]}{capability[1]}"
        try:
            arch_list = set(torch_module.cuda.get_arch_list())
        except Exception:
            return False
        return arch in arch_list

    @staticmethod
    def _runtime_upgrade_hint() -> str:
        return (
            "Upgrade to a Blackwell-compatible PyTorch build (CUDA 12.8+), "
            "or run inside an NVIDIA NGC PyTorch container for GB10/GB200 support."
        )

    def _validate_torch_runtime(self, torch_module: Any) -> None:
        if os.getenv("YAK_SKIP_TORCH_CAP_CHECK", "").strip().lower() in {"1", "true", "yes"}:
            return
        if not torch_module.cuda.is_available():
            return
        capability = tuple(torch_module.cuda.get_device_capability(0))
        if self._supports_cuda_capability(torch_module, capability):
            return
        raise WorkflowError(
            f"Unsupported CUDA capability {capability} for installed PyTorch runtime. "
            f"{self._runtime_upgrade_hint()}"
        )

    def _load_flux_pipe(self) -> Any:
        if self._flux_pipe is not None:
            return self._flux_pipe

        try:
            import torch
            from diffusers import Flux2KleinPipeline
        except Exception as exc:  # pragma: no cover
            raise WorkflowError(
                "FLUX.2-klein runtime is unavailable; ensure diffusers main + torch are installed"
            ) from exc
        self._validate_torch_runtime(torch)

        pipe = Flux2KleinPipeline.from_pretrained(
            self.image_model_id,
            torch_dtype=torch.bfloat16,
        )
        placement = self._flux_placement_mode()
        if placement == "cpu_offload":
            pipe.enable_model_cpu_offload()
        else:
            if not torch.cuda.is_available():
                raise WorkflowError(
                    "CUDA is required for FLUX placement mode 'cuda'. "
                    "Set YAK_FLUX_PLACEMENT=cpu_offload to force CPU offload."
                )
            pipe.to("cuda")
        self._flux_pipe = pipe
        return pipe

    def _generate_image_sync(
        self,
        *,
        prompt: str,
        output_path: Path,
        width: int,
        height: int,
        steps: int,
        seed: int,
        guidance_scale: float,
        style: str | None = None,
    ) -> str:
        if not prompt.strip():
            raise WorkflowError("prompt is required")
        backend = self._image_backend()
        if backend == "flux2_cli":
            return self._generate_image_flux2_cli(
                prompt=prompt,
                output_path=output_path,
                width=width,
                height=height,
                steps=steps,
                seed=seed,
                guidance_scale=guidance_scale,
            )
        if backend == "flux_server":
            return self._generate_image_flux_server(
                prompt=prompt,
                output_path=output_path,
                width=width,
                height=height,
                steps=steps,
                seed=seed,
                guidance_scale=guidance_scale,
                style=style,
            )
        if backend != "diffusers":
            raise WorkflowError(
                f"Unsupported YAK_IMAGE_BACKEND='{backend}'. Use 'flux2_cli' or 'diffusers'."
            )

        try:
            import torch
        except Exception as exc:  # pragma: no cover
            raise WorkflowError("torch is required for local image generation") from exc

        pipe = self._load_flux_pipe()
        gen_device = "cuda" if torch.cuda.is_available() and self._flux_placement_mode() != "cpu_offload" else "cpu"
        generator = torch.Generator(device=gen_device).manual_seed(seed)
        result = pipe(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        image = result.images[0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        return str(output_path)

    def _generate_image_flux_server(
        self,
        *,
        prompt: str,
        output_path: Path,
        width: int,
        height: int,
        steps: int,
        seed: int,
        guidance_scale: float,
        style: str | None = None,
    ) -> str:
        try:
            rel = output_path.resolve().relative_to(self.project_root / "storage")
        except Exception as exc:
            raise WorkflowError(
                "flux_server backend requires output_path under project storage/ so it can be written via volume mount"
            ) from exc

        url = f"{self._flux_server_url()}/generate_image"
        payload = {
            "prompt": prompt,
            "width": int(width),
            "height": int(height),
            "steps": int(steps),
            "seed": int(seed),
            "guidance_scale": float(guidance_scale),
            "output_relpath": str(rel),
        }
        if style:
            payload["style"] = style

        try:
            with httpx.Client(timeout=self.image_timeout_seconds) as client:
                resp = client.post(url, json=payload)
        except Exception as exc:
            raise WorkflowError(f"flux_server request failed: {type(exc).__name__}: {exc}") from exc

        if resp.status_code >= 400:
            raise WorkflowError(f"flux_server error ({resp.status_code}): {resp.text[:400]}")

        out = output_path.resolve()
        if not out.exists():
            raise WorkflowError(f"flux_server reported success but file not found: {out}")
        return str(out)

    def _generate_image_flux2_cli(
        self,
        *,
        prompt: str,
        output_path: Path,
        width: int,
        height: int,
        steps: int,
        seed: int,
        guidance_scale: float,
    ) -> str:
        repo = self._discover_flux2_repo()
        model_name = os.getenv("YAK_FLUX2_MODEL", "flux.2-klein-9b").strip() or "flux.2-klein-9b"
        python_bin = os.getenv("YAK_FLUX2_PYTHON", "").strip() or sys.executable

        # Distilled klein variants require fixed settings.
        if "klein" in model_name.lower():
            steps = 4
            guidance_scale = 1.0

        output_dir = repo / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        before = {p.resolve() for p in output_dir.glob("sample_*.png")}

        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        env.setdefault("FLUX2_SKIP_CONTENT_FILTERS", "1")
        cmd = [
            python_bin,
            "scripts/cli.py",
            f"--model_name={model_name}",
            "--single_eval=True",
            f"--prompt={prompt}",
            f"--width={width}",
            f"--height={height}",
            f"--num_steps={steps}",
            f"--guidance={guidance_scale}",
            f"--seed={seed}",
        ]
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(repo),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.image_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkflowError(
                f"Official flux2 CLI timed out after {self.image_timeout_seconds:.0f}s"
            ) from exc

        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()[-1200:]
            raise WorkflowError(
                "Official flux2 CLI failed. "
                f"Exit={completed.returncode}. Tail: {tail}"
            )

        created = [p for p in output_dir.glob("sample_*.png") if p.resolve() not in before]
        if not created:
            all_samples = list(output_dir.glob("sample_*.png"))
            if not all_samples:
                tail = (completed.stdout or completed.stderr or "").strip()[-1200:]
                raise WorkflowError(f"flux2 CLI returned no output image. Tail: {tail}")
            created = [max(all_samples, key=lambda p: p.stat().st_mtime)]

        newest = max(created, key=lambda p: p.stat().st_mtime)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(newest, output_path)
        return str(output_path)

    def _headers(self) -> dict[str, str]:
        if not self.fal_api_key:
            raise WorkflowError("FAL_KEY is not configured")
        return {
            "Authorization": f"Key {self.fal_api_key}",
            "Content-Type": "application/json",
        }

    def _image_to_data_uri(self, image_path: str) -> str:
        path = Path(image_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "image/png"
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{payload}"

    async def _fal_submit(self, payload: dict[str, Any]) -> str:
        url = f"{self.fal_queue_base}/{self.fal_image_model}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise WorkflowError(f"Fal submit failed ({resp.status_code}): {resp.text[:300]}")
            body = resp.json()
            request_id = body.get("request_id")
            if not request_id:
                raise WorkflowError("Fal submit response missing request_id")
            self._fal_request_urls[str(request_id)] = {
                "status_url": str(body.get("status_url", "")).strip(),
                "response_url": str(body.get("response_url", "")).strip(),
            }
            return str(request_id)

    async def _fal_status(self, request_id: str) -> dict[str, Any]:
        status_url = self._fal_request_urls.get(request_id, {}).get("status_url", "")
        if not status_url:
            status_url = f"{self.fal_queue_base}/{self.fal_image_model}/requests/{request_id}/status"
        request_url = f"{self.fal_queue_base}/{self.fal_image_model}/requests/{request_id}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(status_url, headers=self._headers(), params={"logs": "1"})
            if resp.status_code == 405:
                # Some Fal routes expose status on /requests/{id} and reject /status.
                fallback = await client.get(request_url, headers=self._headers(), params={"logs": "1"})
                if fallback.status_code >= 400:
                    raise WorkflowError(
                        f"Fal status fallback failed ({fallback.status_code}): {fallback.text[:300]}"
                    )
                body = fallback.json()
                if "status" not in body:
                    body["status"] = "COMPLETED" if body.get("response") else "IN_PROGRESS"
                return body
            if resp.status_code >= 400:
                raise WorkflowError(f"Fal status failed ({resp.status_code}): {resp.text[:300]}")
            return resp.json()

    async def _fal_result(self, request_id: str) -> dict[str, Any]:
        url = self._fal_request_urls.get(request_id, {}).get("response_url", "")
        if not url:
            url = f"{self.fal_queue_base}/{self.fal_image_model}/requests/{request_id}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code >= 400:
                raise WorkflowError(f"Fal result failed ({resp.status_code}): {resp.text[:300]}")
            return resp.json()

    def _extract_video_url(self, payload: dict[str, Any]) -> str:
        body = payload.get("response", payload)
        candidate = body.get("video")
        if isinstance(candidate, dict) and candidate.get("url"):
            return str(candidate["url"])
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, dict) and item.get("url"):
                    return str(item["url"])
        videos = body.get("videos")
        if isinstance(videos, list):
            for item in videos:
                if isinstance(item, dict) and item.get("url"):
                    return str(item["url"])
        raise WorkflowError("Fal result does not include a video URL")

    async def _download_video(self, url: str, output_path: Path) -> str:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                raise WorkflowError(f"Fal media download failed ({resp.status_code}): {resp.text[:300]}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(resp.content)
            return str(output_path)

    def _compose_video_prompt(self, prompt: str, video_prompt: str | None = None) -> str:
        base = (video_prompt or "").strip() or prompt.strip()
        return (
            f"{base}. Animate this exact image immediately. "
            "Preserve character identity, species, scene composition, and visual style. "
            "Use smooth, believable motion with subtle camera movement and no hard cuts. "
            "Do not redraw or replace subjects; motion only."
        )

    async def _generate_video_from_image(
        self,
        *,
        prompt: str,
        image_path: str,
        output_path: Path,
        duration: int,
        aspect_ratio: str,
        video_prompt: str | None = None,
    ) -> tuple[str, str, str]:
        motion_prompt = self._compose_video_prompt(prompt, video_prompt)
        payload = {
            "prompt": motion_prompt,
            "start_image_url": self._image_to_data_uri(image_path),
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
            "generate_audio": False,
        }
        request_id = await self._fal_submit(payload)

        elapsed = 0.0
        while True:
            status = await self._fal_status(request_id)
            state = str(status.get("status", "")).upper()
            if state == "COMPLETED":
                break
            if state in {"FAILED", "CANCELLED", "ERROR"}:
                raise WorkflowError(f"Fal request {request_id} failed with status: {state}")
            elapsed += self.poll_interval_seconds
            if elapsed > self.poll_timeout_seconds:
                raise WorkflowError(f"Fal request {request_id} timed out after {elapsed:.0f}s")
            await asyncio.sleep(self.poll_interval_seconds)

        result = await self._fal_result(request_id)
        video_url = self._extract_video_url(result)
        video_path = await self._download_video(video_url, output_path)
        return video_path, request_id, video_url

    async def run(
        self,
        *,
        prompt: str,
        user_id: str,
        session_id: str,
        width: int = 768,
        height: int = 768,
        steps: int = 4,
        seed: int = 7,
        guidance_scale: float = 1.0,
        duration: int = 5,
        aspect_ratio: str = "1:1",
        video_prompt: str | None = None,
        style: str | None = None,
    ) -> WorkflowResult:
        if duration < 3 or duration > 15:
            raise WorkflowError("duration must be between 3 and 15")
        if aspect_ratio not in {"16:9", "9:16", "1:1"}:
            raise WorkflowError("aspect_ratio must be one of 16:9, 9:16, 1:1")

        image_path = self._build_image_path(user_id, session_id)
        video_path = self._build_video_path(user_id, session_id)

        try:
            generated_image = await asyncio.wait_for(
                asyncio.to_thread(
                    self._generate_image_sync,
                    prompt=prompt,
                    output_path=image_path,
                    width=width,
                    height=height,
                    steps=steps,
                    seed=seed,
                    guidance_scale=guidance_scale,
                    style=style,
                ),
                timeout=self.image_timeout_seconds,
            )
        except TimeoutError as exc:
            raise WorkflowError(
                f"Image generation timed out after {self.image_timeout_seconds:.0f}s"
            ) from exc

        generated_video, request_id, remote_url = await self._generate_video_from_image(
            prompt=prompt,
            image_path=generated_image,
            output_path=video_path,
            duration=duration,
            aspect_ratio=aspect_ratio,
            video_prompt=video_prompt,
        )

        return WorkflowResult(
            image_path=generated_image,
            video_path=generated_video,
            request_id=request_id,
            remote_url=remote_url,
            image_model=self.image_model_id,
            video_model=self.fal_image_model,
        )

    @staticmethod
    def result_to_json(result: WorkflowResult) -> str:
        return json.dumps(
            {
                "status": "ok",
                "image_path": result.image_path,
                "video_path": result.video_path,
                "request_id": result.request_id,
                "remote_url": result.remote_url,
                "image_model": result.image_model,
                "video_model": result.video_model,
            },
            ensure_ascii=False,
        )
