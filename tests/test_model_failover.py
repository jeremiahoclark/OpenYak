from pathlib import Path
from typing import Any

from yak.agent.loop import AgentLoop
from yak.agent.tools.base import Tool
from yak.bus.queue import MessageBus
from yak.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class FailingTool(Tool):
    @property
    def name(self) -> str:
        return "fail_tool"

    @property
    def description(self) -> str:
        return "Always fails"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        raise RuntimeError("forced failure")


class FakeProvider(LLMProvider):
    def __init__(self):
        super().__init__(api_key=None, api_base=None)
        self.calls = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self.calls += 1
        if self.calls <= 3:
            return LLMResponse(
                content="calling fail tool",
                tool_calls=[ToolCallRequest(id=f"call_{self.calls}", name="fail_tool", arguments={})],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "nemotron-3-nano"


async def test_auto_failover_after_three_tool_failures(tmp_path: Path) -> None:
    provider = FakeProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="nemotron-3-nano",
        fallback_model="glm-4.7-flash:q8_0",
        tool_failover_threshold=3,
        max_iterations=5,
    )

    loop.tools.register(FailingTool())

    response = await loop.process_direct("trigger tools", session_key="cli:test", channel="cli", chat_id="test")

    assert response == "done"
    assert loop.model == "glm-4.7-flash:q8_0"
