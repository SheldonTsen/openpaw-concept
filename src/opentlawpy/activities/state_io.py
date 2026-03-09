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


@activity.defn
async def save_state_activity(input: SaveStateInput) -> SaveStateOutput:
    chat_dir = os.path.join(STATE_DIR, input.chat_id)
    os.makedirs(chat_dir, exist_ok=True)

    file_path = os.path.join(chat_dir, "state.json")
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
    file_path = os.path.join(STATE_DIR, input.chat_id, "state.json")

    if not os.path.exists(file_path):
        logger.info(f"No state file found for {input.chat_id}")
        return LoadStateOutput(conversation_history=[], found=False)

    with open(file_path) as f:
        data = json.load(f)

    history = data.get("conversation_history", [])
    logger.info(f"Loaded state for {input.chat_id} ({len(history)} messages)")
    return LoadStateOutput(conversation_history=history, found=True)
