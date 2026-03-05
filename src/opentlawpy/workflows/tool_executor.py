import asyncio
import shlex
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from opentlawpy.models.tool_activities import (
    ReadFileInput,
    ReadFileOutput,
    BashCommandOutput,
    ToolCommandOutput,
    WriteFileInput,
    WriteFileOutput,
)
from opentlawpy.models.tools import ToolDefinition


async def execute_tool_calls(
    *,
    tool_calls: list[dict],
    tool_definitions: list[ToolDefinition],
) -> list[dict]:
    """Execute tool calls in parallel, returning tool result messages.

    Returns list of {"role": "tool", "tool_call_id": "...", "content": "..."} dicts.
    Errors are caught per-tool and returned as error content (not raised).
    """
    tasks = [
        _execute_single_tool(tool_call=tc, tool_definitions=tool_definitions) for tc in tool_calls
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

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


async def _execute_single_tool(
    *,
    tool_call: dict,
    tool_definitions: list[ToolDefinition],
) -> str:
    """Execute a single tool call and return the result as a string."""
    func = tool_call["function"]
    tool_name = func["name"]
    args = func["arguments"]

    tool_def = _find_tool(name=tool_name, tool_definitions=tool_definitions)
    if tool_def is None:
        return f"Error: Unknown tool '{tool_name}'"

    tool_type = tool_def.metadata.get("type", "cli")

    if tool_type == "activity":
        return await _execute_activity_tool(tool_name=tool_name, args=args)

    # cli tools — build a shell command and execute via execute_bash_command
    command = _build_command(tool_name=tool_name, args=args)
    if command is None:
        return f"Error: Cannot build command for tool '{tool_name}'"

    timeout = args.get("timeout", 30)

    output: ToolCommandOutput = await workflow.execute_activity(
        "execute_bash_command",
        arg=BashCommandOutput(command=command, timeout=timeout),
        result_type=ToolCommandOutput,
        start_to_close_timeout=timedelta(seconds=timeout + 30),
        retry_policy=RetryPolicy(maximum_attempts=2),
    )

    if output.success:
        return output.stdout or "(no output)"
    return f"Error (exit code {output.exit_code}): {output.stderr or output.stdout}"


async def _execute_activity_tool(*, tool_name: str, args: dict) -> str:
    """Execute an activity-type tool (read_file, write_file)."""
    if tool_name == "read_file":
        output: ReadFileOutput = await workflow.execute_activity(
            "read_file_activity",
            arg=ReadFileInput(
                path=args["path"],
                encoding=args.get("encoding", "utf-8"),
            ),
            result_type=ReadFileOutput,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        if output.success:
            return output.content
        return f"Error: {output.error}"

    if tool_name == "write_file":
        output: WriteFileOutput = await workflow.execute_activity(
            "write_file_activity",
            arg=WriteFileInput(
                path=args["path"],
                content=args["content"],
                mode=args.get("mode", "overwrite"),
            ),
            result_type=WriteFileOutput,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        if output.success:
            return f"Successfully wrote {output.bytes_written} bytes to {args['path']}"
        return f"Error: {output.error}"

    return f"Error: Unknown activity tool '{tool_name}'"


def _find_tool(*, name: str, tool_definitions: list[ToolDefinition]) -> ToolDefinition | None:
    """Find a tool definition by name."""
    for tool in tool_definitions:
        if tool.name == name:
            return tool
    return None


def _build_command(*, tool_name: str, args: dict) -> str | None:
    """Build a shell command string for a CLI tool.

    Uses explicit per-tool logic with shlex.quote for safety.
    """
    if tool_name == "bash":
        return args["command"]

    if tool_name == "git":
        return f"git {args['command']}"

    if tool_name == "python":
        return f"python3 -c {shlex.quote(args['code'])}"

    if tool_name == "calculator":
        expr = args["expression"]
        return f"python3 -c {shlex.quote(f'print({expr})')}"

    if tool_name == "grep":
        parts = ["grep"]
        if not args.get("case_sensitive", False):
            parts.append("-i")
        if args.get("recursive", True):
            parts.append("-rn")
        parts.append(shlex.quote(args["pattern"]))
        parts.append(shlex.quote(args.get("path", ".")))
        return " ".join(parts)

    if tool_name == "web_search":
        return None  # Not implemented

    return None
