"""Shared tool result helpers."""

from __future__ import annotations

from typing import Any


def structured_tool_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    provider: str = "yak",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a standard tool error payload the agent can reason over."""
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "provider": provider,
            "details": details or {},
        },
    }
