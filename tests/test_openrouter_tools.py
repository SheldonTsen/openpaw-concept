import json
from unittest.mock import AsyncMock, patch

import httpx

from openpaw.llm.openrouter_client import OPENROUTER_BASE_URL, OpenRouterClient


def _make_mock_response(*, data: dict) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json=data,
        request=httpx.Request("POST", OPENROUTER_BASE_URL),
    )


def _patch_httpx(mock_response: httpx.Response):
    """Return a patch context manager that stubs httpx.AsyncClient."""
    patcher = patch("openpaw.llm.openrouter_client.httpx.AsyncClient")

    def setup(mock_client_cls):
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance
        return mock_instance

    return patcher, setup


SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a bash command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }
]


async def test_chat_with_tools_sends_tools_in_payload():
    """When tools are provided, they are included in the API payload."""
    data = {
        "choices": [{"message": {"content": "Sure!", "tool_calls": None}, "finish_reason": "stop"}],
        "model": "test-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    mock_response = _make_mock_response(data=data)
    patcher, setup = _patch_httpx(mock_response)

    with patcher as mock_cls:
        mock_instance = setup(mock_cls)

        client = OpenRouterClient(api_key="sk-test")
        await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
            max_tokens=1024,
            tools=SAMPLE_TOOLS,
        )

    call_kwargs = mock_instance.post.call_args
    sent_payload = call_kwargs.kwargs["json"]
    assert sent_payload["tools"] == SAMPLE_TOOLS


async def test_chat_parses_tool_calls_response():
    """Tool calls in the response are parsed with arguments as dicts."""
    data = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": "ls -la"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "model": "test-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    mock_response = _make_mock_response(data=data)
    patcher, setup = _patch_httpx(mock_response)

    with patcher as mock_cls:
        setup(mock_cls)

        client = OpenRouterClient(api_key="sk-test")
        result = await client.chat(
            messages=[{"role": "user", "content": "List files"}],
            model="test-model",
            max_tokens=1024,
            tools=SAMPLE_TOOLS,
        )

    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc["id"] == "call_abc"
    assert tc["function"]["name"] == "bash"
    assert tc["function"]["arguments"] == {"command": "ls -la"}
    assert isinstance(tc["function"]["arguments"], dict)
    assert result.response_text == ""
    assert result.stop_reason == "tool_calls"


async def test_chat_handles_no_tool_calls():
    """When no tool_calls in response, tool_calls list is empty and stop_reason is set."""
    data = {
        "choices": [
            {
                "message": {"content": "Hello!", "role": "assistant"},
                "finish_reason": "stop",
            }
        ],
        "model": "test-model",
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }
    mock_response = _make_mock_response(data=data)
    patcher, setup = _patch_httpx(mock_response)

    with patcher as mock_cls:
        setup(mock_cls)

        client = OpenRouterClient(api_key="sk-test")
        result = await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
            max_tokens=1024,
        )

    assert result.tool_calls == []
    assert result.response_text == "Hello!"
    assert result.stop_reason == "stop"
