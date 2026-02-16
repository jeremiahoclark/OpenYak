from pathlib import Path
from typing import Any

from yak.agent.context import ContextBuilder
from yak.agent.tool_runtime import apply_tool_calls, extract_tool_calls_from_content
from yak.agent.tools.base import Tool
from yak.agent.tools.registry import ToolRegistry
from yak.providers.base import ToolCallRequest


class EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo input"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return f"echo:{kwargs['text']}"


def test_extract_tool_calls_from_json_block() -> None:
    content = 'I will call a tool.```json\n{"tool":"echo","arguments":{"text":"hi"}}\n```'
    calls = extract_tool_calls_from_content(content)
    assert len(calls) == 1
    assert calls[0].name == "echo"
    assert calls[0].arguments == {"text": "hi"}


def test_extract_tool_calls_from_action_input() -> None:
    content = 'Thought: use tool\nAction: echo\nAction Input: {"text":"hello"}'
    calls = extract_tool_calls_from_content(content)
    assert len(calls) == 1
    assert calls[0].name == "echo"
    assert calls[0].arguments == {"text": "hello"}


async def test_apply_tool_calls_appends_tool_results(tmp_path: Path) -> None:
    context = ContextBuilder(tmp_path)
    registry = ToolRegistry()
    registry.register(EchoTool())

    messages: list[dict[str, Any]] = [{"role": "system", "content": "test"}]
    tool_calls = [ToolCallRequest(id="call_1", name="echo", arguments={"text": "world"})]

    updated, tool_results = await apply_tool_calls(
        messages=messages,
        context=context,
        tools=registry,
        tool_calls=tool_calls,
        assistant_content="calling tool",
        reasoning_content=None,
    )

    assert tool_results == ["echo:world"]
    assert updated[-1]["role"] == "tool"
    assert updated[-1]["name"] == "echo"
    assert updated[-1]["content"] == "echo:world"
