from unittest.mock import AsyncMock, patch

import httpx
import pytest

from openpaw.config import LLM_TIMEOUT_SECONDS
from openpaw.llm.openrouter_client import OPENROUTER_BASE_URL, OpenRouterClient


async def test_openrouter_client_sends_correct_request():
    """OpenRouterClient posts correct payload and headers to OpenRouter API."""
    mock_response_data = {
        "choices": [{"message": {"content": "Hello from OpenRouter!"}}],
        "model": "openrouter/free",
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_response_data,
        request=httpx.Request("POST", OPENROUTER_BASE_URL),
    )

    with patch("openpaw.llm.openrouter_client.httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        client = OpenRouterClient(api_key="sk-or-test-key")
        result = await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="openrouter/free",
            max_tokens=1024,
        )

    assert result.response_text == "Hello from OpenRouter!"
    assert result.model_used == "openrouter/free"
    assert result.input_tokens == 12
    assert result.output_tokens == 7

    mock_instance.post.assert_called_once_with(
        url=OPENROUTER_BASE_URL,
        headers={
            "Authorization": "Bearer sk-or-test-key",
            "Content-Type": "application/json",
        },
        json={
            "model": "openrouter/free",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "Hi"}],
        },
        timeout=LLM_TIMEOUT_SECONDS,
    )


async def test_openrouter_client_handles_missing_usage():
    """OpenRouterClient defaults token counts to 0 when usage is missing."""
    mock_response_data = {
        "choices": [{"message": {"content": "response"}}],
        "model": "openrouter/free",
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_response_data,
        request=httpx.Request("POST", OPENROUTER_BASE_URL),
    )

    with patch("openpaw.llm.openrouter_client.httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        client = OpenRouterClient(api_key="sk-or-test-key")
        result = await client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="openrouter/free",
            max_tokens=512,
        )

    assert result.input_tokens == 0
    assert result.output_tokens == 0


async def test_openrouter_client_raises_on_http_error():
    """OpenRouterClient raises on non-2xx responses."""
    mock_response = httpx.Response(
        status_code=429,
        text="Rate limited",
        request=httpx.Request("POST", OPENROUTER_BASE_URL),
    )

    with patch("openpaw.llm.openrouter_client.httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        client = OpenRouterClient(api_key="sk-or-test-key")
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="openrouter/free",
                max_tokens=512,
            )
