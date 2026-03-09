from unittest.mock import AsyncMock

import pytest

from opentlawpy.activities.compaction import SUMMARIZATION_PROMPT, create_compact_history_activity
from opentlawpy.models.compaction import CompactHistoryInput
from opentlawpy.models.llm import LLMCallOutput


@pytest.fixture
def mock_llm_client():
    client = AsyncMock()
    client.chat.return_value = LLMCallOutput(
        response_text="Summary of the conversation so far.",
        model_used="test-model",
        input_tokens=100,
        output_tokens=50,
    )
    return client


@pytest.fixture
def compact_activity(mock_llm_client):
    return create_compact_history_activity(llm_client=mock_llm_client)


def _make_history(n: int) -> list[dict]:
    """Generate n alternating user/assistant messages."""
    history = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"Message {i}"})
    return history


async def test_compaction_calls_llm(compact_activity, mock_llm_client):
    """Verify LLM is called with correct messages and result has summary + last 2."""
    history = _make_history(10)
    input_data = CompactHistoryInput(conversation_history=history)

    output = await compact_activity(input_data)

    mock_llm_client.chat.assert_called_once()
    call_kwargs = mock_llm_client.chat.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-5-20250929"
    assert call_kwargs["max_tokens"] == 2048
    assert call_kwargs["tools"] is None

    # First message in LLM call should be the summarization prompt
    llm_messages = call_kwargs["messages"]
    assert llm_messages[0] == {"role": "system", "content": SUMMARIZATION_PROMPT}
    # Last message should be the trigger
    assert llm_messages[-1] == {"role": "user", "content": "Please provide the summary now."}
    # Middle messages should be history[:-2]
    assert llm_messages[1:-1] == history[:-2]

    # Output: 1 summary + 2 kept = 3
    assert output.compacted_message_count == 3
    assert output.original_message_count == 10


async def test_summary_message_format(compact_activity, mock_llm_client):
    """Summary message has [CONVERSATION SUMMARY] prefix and system role."""
    history = _make_history(6)
    input_data = CompactHistoryInput(conversation_history=history)

    output = await compact_activity(input_data)

    summary_msg = output.compacted_history[0]
    assert summary_msg["role"] == "system"
    assert summary_msg["content"].startswith("[CONVERSATION SUMMARY]")
    assert "Summary of the conversation so far." in summary_msg["content"]


async def test_last_exchange_preserved(compact_activity, mock_llm_client):
    """Last 2 messages of original history are preserved verbatim."""
    history = _make_history(8)
    input_data = CompactHistoryInput(conversation_history=history)

    output = await compact_activity(input_data)

    assert output.compacted_history[-2:] == history[-2:]


async def test_compaction_with_tool_call_messages(compact_activity, mock_llm_client):
    """Compaction handles tool call messages in history."""
    history = [
        {"role": "user", "content": "List files"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "1", "function": {"name": "bash"}}],
        },
        {"role": "tool", "tool_call_id": "1", "content": "file1.txt"},
        {"role": "assistant", "content": "Here are the files."},
        {"role": "user", "content": "Thanks"},
        {"role": "assistant", "content": "You're welcome!"},
    ]
    input_data = CompactHistoryInput(conversation_history=history)

    output = await compact_activity(input_data)

    # LLM should receive all messages except last 2 for summarization
    call_kwargs = mock_llm_client.chat.call_args.kwargs
    llm_messages = call_kwargs["messages"]
    # system prompt + history[:-2] (4 msgs) + trigger = 6
    assert len(llm_messages) == 6

    # Last 2 preserved
    assert output.compacted_history[-2:] == history[-2:]
    assert output.compacted_message_count == 3
