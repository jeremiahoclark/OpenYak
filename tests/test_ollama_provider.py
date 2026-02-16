import httpx

from yak.providers.ollama_provider import OllamaProvider


class _RaisingClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")

    async def get(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")


async def test_ollama_chat_connect_error(monkeypatch):
    monkeypatch.setattr("yak.providers.ollama_provider.httpx.AsyncClient", _RaisingClient)
    provider = OllamaProvider(api_base="http://127.0.0.1:11434", default_model="glm-4.7-flash:q8_0")

    response = await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert response.finish_reason == "error"
    assert response.content is not None
    assert "Error calling Ollama" in response.content


async def test_ollama_healthcheck_failure(monkeypatch):
    monkeypatch.setattr("yak.providers.ollama_provider.httpx.AsyncClient", _RaisingClient)
    provider = OllamaProvider()
    assert await provider.healthcheck() is False


def test_ollama_parse_response_with_tool_call():
    provider = OllamaProvider()
    raw = {
        "done_reason": "tool_calls",
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "echo",
                        "arguments": '{"text":"hi"}',
                    },
                }
            ],
        },
        "prompt_eval_count": 10,
        "eval_count": 5,
    }

    parsed = provider._parse_response(raw)
    assert parsed.has_tool_calls
    assert parsed.tool_calls[0].name == "echo"
    assert parsed.tool_calls[0].arguments == {"text": "hi"}
    assert parsed.usage["total_tokens"] == 15
