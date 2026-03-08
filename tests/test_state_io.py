import json

import pytest

from opentlawpy.activities.state_io import load_state_activity, save_state_activity
from opentlawpy.models.state import LoadStateInput, SaveStateInput


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("opentlawpy.activities.state_io.STATE_DIR", str(tmp_path))
    return tmp_path


async def test_save_and_load_state(state_dir):
    """Round-trip: save then load, verify history matches."""
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    save_result = await save_state_activity(
        SaveStateInput(chat_id="test-chat-123", conversation_history=history)
    )
    assert save_result.success is True

    load_result = await load_state_activity(LoadStateInput(chat_id="test-chat-123"))
    assert load_result.found is True
    assert load_result.conversation_history == history


async def test_load_nonexistent_state(state_dir):
    """Returns empty history with found=False when no state file exists."""
    load_result = await load_state_activity(LoadStateInput(chat_id="nonexistent-chat"))
    assert load_result.found is False
    assert load_result.conversation_history == []


async def test_save_creates_directory(state_dir):
    """Auto-creates state/{chat_id}/ directory if missing."""
    chat_id = "new-chat-456"
    chat_dir = state_dir / chat_id
    assert not chat_dir.exists()

    await save_state_activity(
        SaveStateInput(chat_id=chat_id, conversation_history=[{"role": "user", "content": "test"}])
    )

    assert chat_dir.exists()
    assert (chat_dir / "state.json").exists()


async def test_save_writes_valid_json(state_dir):
    """State file contains valid JSON with expected fields."""
    history = [{"role": "user", "content": "Hi"}]

    await save_state_activity(
        SaveStateInput(chat_id="json-test", conversation_history=history)
    )

    file_path = state_dir / "json-test" / "state.json"
    with open(file_path) as f:
        data = json.load(f)

    assert data["chat_id"] == "json-test"
    assert data["conversation_history"] == history
    assert "last_updated" in data


async def test_save_overwrites_existing_state(state_dir):
    """Saving again overwrites the previous state."""
    chat_id = "overwrite-test"

    await save_state_activity(
        SaveStateInput(
            chat_id=chat_id,
            conversation_history=[{"role": "user", "content": "first"}],
        )
    )

    new_history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "response"},
        {"role": "user", "content": "second"},
    ]
    await save_state_activity(
        SaveStateInput(chat_id=chat_id, conversation_history=new_history)
    )

    load_result = await load_state_activity(LoadStateInput(chat_id=chat_id))
    assert load_result.conversation_history == new_history
