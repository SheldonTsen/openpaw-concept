from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opentlawpy.activities.llm_call import create_call_llm_activity
from opentlawpy.llm.anthropic_client import AnthropicClient
from opentlawpy.models.llm import LLMCallInput, LLMCallOutput


async def test_call_llm_activity_returns_response():
    """Activity delegates to AnthropicClient and returns LLMCallOutput."""
    mock_client = AsyncMock(spec=AnthropicClient)
    expected_output = LLMCallOutput(
        response_text="Hello!",
        model_used="claude-sonnet-4-5-20250929",
        input_tokens=10,
        output_tokens=5,
    )
    mock_client.chat.return_value = expected_output

    call_llm = create_call_llm_activity(anthropic_client=mock_client)

    input_data = LLMCallInput(messages=[{"role": "user", "content": "Hi"}])
    result = await call_llm(input_data)

    assert result == expected_output
    mock_client.chat.assert_called_once_with(
        messages=[{"role": "user", "content": "Hi"}],
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
    )


async def test_call_llm_activity_propagates_errors():
    """Activity propagates exceptions from AnthropicClient for Temporal to retry."""
    mock_client = AsyncMock(spec=AnthropicClient)
    mock_client.chat.side_effect = RuntimeError("API rate limited")

    call_llm = create_call_llm_activity(anthropic_client=mock_client)

    input_data = LLMCallInput(messages=[{"role": "user", "content": "Hi"}])
    with pytest.raises(RuntimeError, match="API rate limited"):
        await call_llm(input_data)


async def test_anthropic_client_chat():
    """AnthropicClient.chat() calls the SDK and maps the response correctly."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="I'm Claude")]
    mock_response.model = "claude-sonnet-4-5-20250929"
    mock_response.usage.input_tokens = 15
    mock_response.usage.output_tokens = 8

    with patch("opentlawpy.llm.anthropic_client.anthropic.AsyncAnthropic") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.messages.create.return_value = mock_response
        mock_cls.return_value = mock_instance

        client = AnthropicClient(api_key="test-key")
        result = await client.chat(
            messages=[{"role": "user", "content": "Hello"}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
        )

    assert result.response_text == "I'm Claude"
    assert result.model_used == "claude-sonnet-4-5-20250929"
    assert result.input_tokens == 15
    assert result.output_tokens == 8
    mock_instance.messages.create.assert_called_once_with(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello"}],
    )
