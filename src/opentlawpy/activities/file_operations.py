import logging
import os

from temporalio import activity

from opentlawpy.config import WORKSPACE_DIR
from opentlawpy.models.tool_activities import (
    ReadFileInput,
    ReadFileOutput,
    WriteFileInput,
    WriteFileOutput,
)

logger = logging.getLogger(__name__)

MAX_READ_BYTES = 1_000_000


def _resolve_safe_path(path: str) -> str:
    """Resolve path and verify it stays within WORKSPACE_DIR.

    Raises ValueError if the resolved path escapes the workspace boundary.
    """
    workspace = os.path.realpath(WORKSPACE_DIR)
    resolved = os.path.realpath(os.path.join(workspace, path))

    if not resolved.startswith(workspace + os.sep) and resolved != workspace:
        raise ValueError(f"Path traversal detected: {path!r} resolves outside workspace")

    return resolved


@activity.defn(name="read_file_activity")
async def read_file_activity(input: ReadFileInput) -> ReadFileOutput:
    try:
        resolved = _resolve_safe_path(input.path)
    except ValueError as e:
        return ReadFileOutput(content="", success=False, error=str(e))

    if not os.path.exists(resolved):
        return ReadFileOutput(
            content="",
            success=False,
            error=f"File not found: {input.path}",
        )

    file_size = os.path.getsize(resolved)
    if file_size > MAX_READ_BYTES:
        return ReadFileOutput(
            content="",
            success=False,
            error=f"File too large: {file_size} bytes (max {MAX_READ_BYTES})",
        )

    logger.info("Reading file: %s", resolved)

    with open(resolved, encoding=input.encoding) as f:
        content = f.read()

    return ReadFileOutput(content=content, success=True)


@activity.defn(name="write_file_activity")
async def write_file_activity(input: WriteFileInput) -> WriteFileOutput:
    try:
        resolved = _resolve_safe_path(input.path)
    except ValueError as e:
        return WriteFileOutput(success=False, error=str(e))

    os.makedirs(os.path.dirname(resolved), exist_ok=True)

    logger.info("Writing file (%s): %s", input.mode, resolved)

    file_mode = "a" if input.mode == "append" else "w"

    with open(resolved, mode=file_mode) as f:
        bytes_written = f.write(input.content)

    return WriteFileOutput(success=True, bytes_written=bytes_written)
