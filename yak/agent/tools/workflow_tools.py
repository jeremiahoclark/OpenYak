"""Agent tool wrappers for workflow orchestration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from yak.agent.tools.base import Tool
from yak.workflows.text_to_video import TextToVideoWorkflow


_DEFAULT_STYLE_SUFFIX = """[yak_style:v1]
Lyrical modern anime illustration with delicate, clean linework and soft watercolor-like shading.
Pastel spring palette (peach, soft blue, mint, warm cream), gentle gradients, subtle bloom.
Cinematic natural lighting (golden hour rim light + soft fill), realistic light falloff.
Shallow depth of field with tasteful bokeh highlights; mild film grain.
Expressive eyes with nuanced highlights; natural facial proportions; understated blush.
Highly detailed hair strands with soft translucency; cloth folds rendered with painterly softness.
Background: airy urban/suburban Japan-inspired streets or park; cherry blossoms drifting; crisp architecture.
Mood: tender, hopeful, emotionally resonant; calm motion; no chibi, no harsh cel shading.
Composition: rule-of-thirds, foreground blossom/petal framing, gentle atmospheric perspective.
Color grading: warm highlights, cool shadows, balanced saturation (avoid neon).
"""


def _load_style_suffix() -> str:
    """Load a style suffix from env or workspace/STYLE.md.

    Precedence:
    1) YAK_STYLE_SUFFIX (inline text)
    2) YAK_STYLE_SUFFIX_PATH (file path)
    3) workspace/STYLE.md (DEFAULT_ANIME_SPRING_V1 block)
    4) built-in default
    """
    inline = os.getenv("YAK_STYLE_SUFFIX", "").strip()
    if inline:
        return inline

    path = os.getenv("YAK_STYLE_SUFFIX_PATH", "").strip()
    if path:
        p = Path(path).expanduser()
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()

    # Best-effort: load from workspace/STYLE.md if present.
    # This tool lives under yak/agent/tools; project root is 4 parents up.
    try:
        project_root = Path(__file__).resolve().parents[4]
        style_md = project_root / "workspace" / "STYLE.md"
        if style_md.is_file():
            text = style_md.read_text(encoding="utf-8")
            # Grab the first fenced block that contains our sentinel.
            start = text.find("```\n[yak_style:v1]")
            if start != -1:
                end = text.find("```", start + 3)
                if end != -1:
                    block = text[start + 3 : end].strip()
                    if block:
                        return block
    except Exception:
        pass

    return _DEFAULT_STYLE_SUFFIX.strip()


def _append_style(prompt: str, suffix: str) -> str:
    prompt = (prompt or "").strip()
    suffix = (suffix or "").strip()
    if not suffix or "[yak_style:v1]" in prompt:
        return prompt
    if not prompt:
        return suffix
    return f"{prompt}\n\nSTYLE:\n{suffix}"


class TextToVideoWorkflowTool(Tool):
    """Generate image then video in one orchestrated workflow."""

    # Hard runtime caps (we clamp to these even if the model asks for more).
    MAX_STEPS = 20
    MAX_DURATION = 15

    def __init__(
        self,
        workflow: TextToVideoWorkflow,
        *,
        default_user_id: str = "default",
        default_session_id: str = "default",
    ):
        self.workflow = workflow
        self._default_user_id = default_user_id
        self._default_session_id = default_session_id
        self._style_suffix = _load_style_suffix()

    def set_context(self, *, user_id: str, session_id: str) -> None:
        self._default_user_id = user_id or self._default_user_id
        self._default_session_id = session_id or self._default_session_id

    @property
    def name(self) -> str:
        return "text_to_video_workflow"

    @property
    def description(self) -> str:
        return (
            "Create a video from a text prompt by first generating a local image "
            "with FLUX.2-klein-9B, then sending that image to Fal image-to-video. "
            f"Note: steps > {self.MAX_STEPS} and duration > {self.MAX_DURATION}s will be clamped. "
            "A default anime style suffix may be appended unless overridden. "
            "Available art styles (via LoRA): arcane, cyanide_and_happiness, devil_may_cry."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        # Accept a wider range than runtime caps so the tool does not fail validation
        # when the LLM proposes bigger values; we clamp inside execute().
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1},
                "width": {"type": "integer", "minimum": 256, "maximum": 1536},
                "height": {"type": "integer", "minimum": 256, "maximum": 1536},
                "steps": {"type": "integer", "minimum": 1, "maximum": 60},
                "seed": {"type": "integer"},
                "guidance_scale": {"type": "number", "minimum": 0.1, "maximum": 10.0},
                "duration": {"type": "integer", "minimum": 3, "maximum": 60},
                "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1"]},
                "video_prompt": {"type": "string"},
                "style": {
                    "type": "string",
                    "enum": ["arcane", "cyanide_and_happiness", "devil_may_cry"],
                    "description": "LoRA art style to apply. arcane=Arcane League of Legends, cyanide_and_happiness=stick figure webcomic, devil_may_cry=DMC game style.",
                },
                "user_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str,
        width: int = 768,
        height: int = 768,
        steps: int = 4,
        seed: int = 7,
        guidance_scale: float = 1.0,
        duration: int = 5,
        aspect_ratio: str = "1:1",
        video_prompt: str | None = None,
        style: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        resolved_user_id = (user_id or self._default_user_id).strip() or "default"
        resolved_session_id = (session_id or self._default_session_id).strip() or "default"

        eff_steps = max(1, min(int(steps), self.MAX_STEPS))
        eff_duration = max(3, min(int(duration), self.MAX_DURATION))
        eff_width = max(256, min(int(width), 1536))
        eff_height = max(256, min(int(height), 1536))
        eff_seed = max(0, int(seed))
        eff_guidance = float(guidance_scale)

        styled_prompt = _append_style(prompt, self._style_suffix)

        eff_video_prompt = (video_prompt or "").strip() or (
            f"Animate the scene smoothly. Add natural motion consistent with: {prompt.strip()}"
        )
        eff_video_prompt = _append_style(eff_video_prompt, self._style_suffix)

        result = await self.workflow.run(
            prompt=styled_prompt,
            user_id=resolved_user_id,
            session_id=resolved_session_id,
            width=eff_width,
            height=eff_height,
            steps=eff_steps,
            seed=eff_seed,
            guidance_scale=eff_guidance,
            duration=eff_duration,
            aspect_ratio=aspect_ratio,
            video_prompt=eff_video_prompt,
            style=style,
        )

        payload = json.loads(TextToVideoWorkflow.result_to_json(result))
        if isinstance(payload, dict):
            payload["effective_params"] = {
                "width": eff_width,
                "height": eff_height,
                "steps": eff_steps,
                "seed": eff_seed,
                "guidance_scale": eff_guidance,
                "duration": eff_duration,
                "aspect_ratio": aspect_ratio,
                "video_prompt": eff_video_prompt,
                "style": style,
            }
            payload["style_suffix_applied"] = True
        return json.dumps(payload, ensure_ascii=False)
