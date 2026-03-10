import logging
from typing import Any, Callable

from temporalio import activity

from opentlawpy.config import COMPACTION_KEEP_RECENT
from opentlawpy.models.compaction import CompactHistoryInput, CompactHistoryOutput

logger = logging.getLogger(__name__)

SUMMARIZATION_PROMPT = (
    "You are a conversation summarizer. Summarize the following conversation history "
    "into a concise summary that preserves all important context, decisions, tool calls "
    "and their results, and key information. The summary will replace the original messages "
    "to save space, so be thorough but concise. Include any file paths, commands, errors, "
    "or other technical details that may be needed for context."
)


def create_compact_history_activity(*, llm_client: Any) -> Callable:
    @activity.defn(name="compact_history")
    async def compact_history(input: CompactHistoryInput) -> CompactHistoryOutput:
        history = input.conversation_history
        original_count = len(history)

        to_summarize = history[:-COMPACTION_KEEP_RECENT]
        to_keep = history[-COMPACTION_KEEP_RECENT:]

        messages = (
            [{"role": "system", "content": SUMMARIZATION_PROMPT}]
            + to_summarize
            + [{"role": "user", "content": "Please provide the summary now."}]
        )

        llm_output = await llm_client.chat(
            messages=messages,
            model=input.model,
            max_tokens=input.max_tokens,
            tools=None,
        )

        summary_message = {
            "role": "system",
            "content": f"[CONVERSATION SUMMARY]\n{llm_output.response_text}",
        }

        compacted = [summary_message] + to_keep

        logger.info(
            "Compacted history from %d to %d messages.",
            original_count,
            len(compacted),
        )

        return CompactHistoryOutput(
            compacted_history=compacted,
            original_message_count=original_count,
            compacted_message_count=len(compacted),
        )

    return compact_history
