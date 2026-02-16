"""Ollama provider implementation using the OpenAI-compatible API."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import httpx

from yak.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class OllamaProvider(LLMProvider):
    """LLM provider backed by a local Ollama server."""

    def __init__(
        self,
        api_base: str = "http://127.0.0.1:11434",
        default_model: str = "glm-4.7-flash:q8_0",
        timeout_seconds: int = 120,
    ):
        super().__init__(api_key=None, api_base=api_base.rstrip("/"))
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if tools:
            payload["tools"] = tools

        endpoint = f"{self.api_base}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(endpoint, json=payload)
                data = response.json()
                if response.status_code >= 400:
                    err = str(data.get("error", response.text))
                    if "can't find closing '}' symbol" in err:
                        self._write_debug_payload("initial_error", payload, err)
                        sanitized_payload = {
                            **payload,
                            "messages": self._sanitize_messages(payload["messages"]),
                        }
                        retry = await client.post(endpoint, json=sanitized_payload)
                        retry_data = retry.json()
                        if retry.status_code < 400:
                            return self._parse_response(retry_data)
                        err = str(retry_data.get("error", retry.text))
                        self._write_debug_payload("retry_error", sanitized_payload, err)
                        if "can't find closing '}' symbol" in err:
                            compact_payload = {
                                **sanitized_payload,
                                "messages": self._compact_messages(sanitized_payload["messages"]),
                            }
                            retry2 = await client.post(endpoint, json=compact_payload)
                            retry2_data = retry2.json()
                            if retry2.status_code < 400:
                                return self._parse_response(retry2_data)
                            err = str(retry2_data.get("error", retry2.text))
                            self._write_debug_payload("compact_retry_error", compact_payload, err)
                    return LLMResponse(content=f"Error calling Ollama: {err}", finish_reason="error")
            return self._parse_response(data)
        except Exception as exc:
            return LLMResponse(
                content=f"Error calling Ollama: {exc}",
                finish_reason="error",
            )

    async def healthcheck(self) -> bool:
        """Return True when Ollama responds on /api/tags."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.api_base}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        message = data.get("message") or {}

        tool_calls: list[ToolCallRequest] = []
        for tc in message.get("tool_calls") or []:
            function = tc.get("function") or {}
            raw_args = function.get("arguments", {})
            args: dict[str, Any]
            if isinstance(raw_args, str):
                try:
                    parsed = json.loads(raw_args)
                    args = parsed if isinstance(parsed, dict) else {"value": parsed}
                except json.JSONDecodeError:
                    args = {"raw": raw_args}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {"value": raw_args}

            tool_calls.append(
                ToolCallRequest(
                    id=tc.get("id") or f"call_{uuid.uuid4().hex[:10]}",
                    name=function.get("name", "unknown_tool"),
                    arguments=args,
                )
            )

        usage = {
            "prompt_tokens": int(data.get("prompt_eval_count", 0)),
            "completion_tokens": int(data.get("eval_count", 0)),
            "total_tokens": int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0)),
        }

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=data.get("done_reason") or "stop",
            usage=usage,
            reasoning_content=message.get("reasoning_content"),
        )

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strip fields/content patterns that commonly trigger Ollama JSON parser failures."""
        sanitized: list[dict[str, Any]] = []
        for msg in messages:
            clean = dict(msg)
            clean.pop("reasoning_content", None)

            if clean.get("role") == "assistant" and clean.get("tool_calls"):
                tool_calls = clean.get("tool_calls") or []
                has_synthetic_tool_calls = False
                for tc in tool_calls:
                    tc_id = str(tc.get("id", ""))
                    fn = tc.get("function") or {}
                    fn_args = fn.get("arguments")
                    if tc_id.startswith("react_") or fn_args == "{}":
                        has_synthetic_tool_calls = True
                        break
                if has_synthetic_tool_calls:
                    clean.pop("tool_calls", None)
                    if not str(clean.get("content") or "").strip():
                        clean["content"] = "Tool call executed."

            if clean.get("role") == "assistant":
                content = clean.get("content")
                if isinstance(content, str) and content.strip().startswith("{"):
                    clean["content"] = ""

            sanitized.append(clean)
        return sanitized

    def _write_debug_payload(self, stage: str, payload: dict[str, Any], error: str) -> None:
        """Persist recent Ollama parser-failure payload for diagnosis."""
        try:
            out = Path.home() / ".yak" / "last_ollama_parser_error.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(
                    {
                        "stage": stage,
                        "error": error,
                        "payload": payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception:
            return

    def _compact_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep system prompt + a short, cleaner tail of conversation."""
        if not messages:
            return messages
        system = messages[0]
        tail = messages[1:]
        kept: list[dict[str, Any]] = []
        for msg in tail[-10:]:
            content = msg.get("content")
            if isinstance(content, str):
                if "{...}" in content:
                    continue
                if "Error calling Ollama: Value looks like object" in content:
                    continue
            kept.append(msg)
        return [system] + kept

    def get_default_model(self) -> str:
        return self.default_model
