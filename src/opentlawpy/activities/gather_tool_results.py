import logging
import os

from temporalio import activity

from opentlawpy.config import WORKSPACE_DIR
from opentlawpy.models.tool_activities import GatherToolResultsInput, GatherToolResultsOutput

logger = logging.getLogger(__name__)


@activity.defn(name="gather_tool_results_activity")
async def gather_tool_results_activity(input: GatherToolResultsInput) -> GatherToolResultsOutput:
    """Gather all results."""
    tool_results_as_messages = []
    for tc, result in zip(input.tool_calls, input.tool_results):
        if isinstance(result, Exception):
            content = f"Error: {result}"
        else:
            content = result

        tool_results_as_messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": content,
            }
        )

    return GatherToolResultsOutput(tool_results_as_messages=tool_results_as_messages)
