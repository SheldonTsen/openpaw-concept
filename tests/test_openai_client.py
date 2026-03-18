from unittest.mock import AsyncMock, patch

import httpx
import pytest

from openpaw.config import LLM_TIMEOUT_SECONDS
from openpaw.llm.openai_client import OpenAIClient

# does not matter
BASE_URL = "http://localhost:8888/v1"


async def test_openai_client_sends_correct_request():
    """OpenAIClient posts correct payload and headers."""
    mock_response_data = {
        "choices": [{"message": {"content": "Hello from local!"}, "finish_reason": "stop"}],
        "model": "default_model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_response_data,
        request=httpx.Request("POST", f"{BASE_URL}/chat/completions"),
    )

    with patch("openpaw.llm.openai_client.httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        client = OpenAIClient(base_url=BASE_URL)
        result = await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="",
            max_tokens=1024,
        )

    assert result.response_text == "Hello from local!"
    assert result.model_used == "default_model"
    assert result.input_tokens == 10
    assert result.output_tokens == 5

    mock_instance.post.assert_called_once_with(
        url=f"{BASE_URL}/chat/completions",
        headers={"Content-Type": "application/json"},
        json={
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
        },
        timeout=LLM_TIMEOUT_SECONDS,
    )


async def test_openai_client_sends_api_key_when_provided():
    """OpenAIClient includes Authorization header when api_key is set."""
    mock_response_data = {
        "choices": [{"message": {"content": "response"}}],
        "model": "some-model",
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_response_data,
        request=httpx.Request("POST", f"{BASE_URL}/chat/completions"),
    )

    with patch("openpaw.llm.openai_client.httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        client = OpenAIClient(base_url=BASE_URL, api_key="sk-test-key")
        await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="some-model",
            max_tokens=512,
        )

    call_kwargs = mock_instance.post.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"


async def test_openai_client_handles_missing_usage():
    """OpenAIClient defaults token counts to 0 when usage is missing."""
    mock_response_data = {
        "choices": [{"message": {"content": "response"}}],
        "model": "default_model",
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_response_data,
        request=httpx.Request("POST", f"{BASE_URL}/chat/completions"),
    )

    with patch("openpaw.llm.openai_client.httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        client = OpenAIClient(base_url=BASE_URL)
        result = await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="",
            max_tokens=512,
        )

    assert result.input_tokens == 0
    assert result.output_tokens == 0


async def test_openai_client_raises_on_http_error():
    """OpenAIClient raises on non-2xx responses."""
    mock_response = httpx.Response(
        status_code=500,
        text="Internal server error",
        request=httpx.Request("POST", f"{BASE_URL}/chat/completions"),
    )

    with patch("openpaw.llm.openai_client.httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        client = OpenAIClient(base_url=BASE_URL)
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="",
                max_tokens=512,
            )
