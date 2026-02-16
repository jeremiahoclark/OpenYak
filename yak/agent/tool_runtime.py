"""Tool execution helpers, including ReAct fallback parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from yak.agent.context import ContextBuilder
from yak.agent.tools.registry import ToolRegistry
from yak.providers.base import ToolCallRequest

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_ACTION_INPUT_RE = re.compile(
    r"Action\s*:\s*([A-Za-z0-9_\-]+)\s*(?:\r?\n)+Action Input\s*:\s*(\{.*\})",
    re.DOTALL,
)
_PAREN_TOOL_RE = re.compile(
    r'\("tool"\s*:\s*"(?P<name>[A-Za-z0-9_\-]+)"\s*,\s*"arguments"\s*:\s*\((?P<args>.*)\)\s*\)',
    re.DOTALL,
)


def _coerce_tool_call(payload: dict[str, Any], idx: int) -> ToolCallRequest | None:
    name = payload.get("tool") or payload.get("name") or payload.get("action")
    arguments = payload.get("arguments") or payload.get("input") or payload.get("args") or {}
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            arguments = parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}
    if not isinstance(name, str) or not name.strip():
        return None
    return ToolCallRequest(id=f"react_{idx}", name=name.strip(), arguments=arguments)


def extract_tool_calls_from_content(content: str | None) -> list[ToolCallRequest]:
    """Parse tool calls from assistant text using loose ReAct conventions."""
    if not content:
        return []

    calls: list[ToolCallRequest] = []
    cursor = 0

    for match in _JSON_BLOCK_RE.finditer(content):
        block = match.group(1)
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            call = _coerce_tool_call(obj, cursor)
            if call:
                calls.append(call)
                cursor += 1

    for match in _ACTION_INPUT_RE.finditer(content):
        name = match.group(1)
        raw_input = match.group(2).strip()
        try:
            args = json.loads(raw_input)
            if not isinstance(args, dict):
                args = {"value": args}
        except json.JSONDecodeError:
            args = {"raw": raw_input}
        calls.append(ToolCallRequest(id=f"react_{cursor}", name=name, arguments=args))
        cursor += 1

    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                call = _coerce_tool_call(obj, cursor)
                if call:
                    calls.append(call)
        except json.JSONDecodeError:
            pass
    elif stripped.startswith("(") and stripped.endswith(")"):
        candidate = "{" + stripped[1:-1].strip() + "}"
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                call = _coerce_tool_call(obj, cursor)
                if call:
                    calls.append(call)
        except json.JSONDecodeError:
            m = _PAREN_TOOL_RE.search(stripped)
            if m:
                name = m.group("name")
                raw_args = m.group("args").strip()
                args: dict[str, Any] = {}
                for piece in [p.strip() for p in raw_args.split(",") if p.strip()]:
                    if "=" not in piece:
                        continue
                    k, v = piece.split("=", 1)
                    key = k.strip().strip('"').strip("'")
                    val = v.strip()
                    if (val.startswith('"') and val.endswith('"')) or (
                        val.startswith("'") and val.endswith("'")
                    ):
                        args[key] = val[1:-1]
                    else:
                        try:
                            args[key] = json.loads(val)
                        except Exception:
                            args[key] = val
                calls.append(ToolCallRequest(id=f"react_{cursor}", name=name, arguments=args))

    deduped: list[ToolCallRequest] = []
    seen: set[tuple[str, str]] = set()
    for call in calls:
        fingerprint = (call.name, json.dumps(call.arguments, sort_keys=True, ensure_ascii=False))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(call)
    return deduped


async def apply_tool_calls(
    *,
    messages: list[dict[str, Any]],
    context: ContextBuilder,
    tools: ToolRegistry,
    tool_calls: list[ToolCallRequest],
    assistant_content: str | None,
    reasoning_content: str | None,
    include_tool_call_message: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Append assistant tool call message and tool outputs to message history."""
    if include_tool_call_message:
        tool_call_dicts = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
            }
            for tc in tool_calls
        ]
        messages = context.add_assistant_message(
            messages,
            assistant_content,
            tool_call_dicts,
            reasoning_content=reasoning_content,
        )
    elif assistant_content:
        messages = context.add_assistant_message(
            messages,
            assistant_content,
            tool_calls=None,
            reasoning_content=None,
        )

    tool_results: list[str] = []
    for tool_call in tool_calls:
        args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
        logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
        result = await tools.execute(tool_call.name, tool_call.arguments)
        tool_results.append(result)
        messages = context.add_tool_result(messages, tool_call.id, tool_call.name, result)
    return messages, tool_results
