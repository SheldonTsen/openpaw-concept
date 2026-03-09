import json
import logging
import os
from datetime import datetime

from temporalio import activity

from opentlawpy.config import STATE_DIR
from opentlawpy.models.state import (
    LoadStateInput,
    LoadStateOutput,
    SaveStateInput,
    SaveStateOutput,
)

logger = logging.getLogger(__name__)


def _state_file_path(chat_id: str) -> str:
    return os.path.join(STATE_DIR, chat_id, "state.json")


@activity.defn
async def save_state_activity(input: SaveStateInput) -> SaveStateOutput:
    file_path = _state_file_path(chat_id=input.chat_id)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w") as f:
        json.dump(
            {
                "chat_id": input.chat_id,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "conversation_history": input.conversation_history,
            },
            f,
            indent=2,
        )

    logger.info(f"Saved state for {input.chat_id} ({len(input.conversation_history)} messages)")
    return SaveStateOutput(success=True)


@activity.defn
async def load_state_activity(input: LoadStateInput) -> LoadStateOutput:
    file_path = _state_file_path(chat_id=input.chat_id)

    if not os.path.exists(file_path):
        logger.info(f"No state file found for {input.chat_id}")
        return LoadStateOutput(conversation_history=[], found=False)

    with open(file_path) as f:
        data = json.load(f)

    history = data.get("conversation_history", [])
    logger.info(f"Loaded state for {input.chat_id} ({len(history)} messages)")
    return LoadStateOutput(conversation_history=history, found=True)
