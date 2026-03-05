import logging
import asyncio
import importlib

from temporalio import workflow

logger = logging.getLogger(__name__)


async def execute_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """Execute tool calls in parallel, returning tool result messages.

    Returns list of {"role": "tool", "tool_call_id": "...", "content": "..."} dicts.
    Errors are caught per-tool and returned as error content (not raised).
    """
    logger.info(f"Calling execute_tool_calls with: {tool_calls}")
    tasks = [_dispatch(tool_call=tc) for tc in tool_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # TODO - break this into a separate activity for better visibility
    # can call this gather results
    messages = []
    for tc, result in zip(tool_calls, results):
        if isinstance(result, Exception):
            content = f"Error: {result}"
        else:
            content = result

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": content,
            }
        )

    return messages


async def _dispatch(tool_call: dict) -> str:
    """Dispatch a single tool call to its handler via importlib convention.

    Tool name "bash" → opentlawpy.tool_handlers.bash → handle(args).
    """
    func = tool_call["function"]
    name = func["name"]
    args = func["arguments"]

    try:
        with workflow.unsafe.imports_passed_through():
            mod = importlib.import_module(f"opentlawpy.tool_handlers.{name}")
    except ModuleNotFoundError:
        return f"Error: Unknown tool '{name}'"

    return await mod.handle(args)
