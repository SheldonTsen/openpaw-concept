import asyncio
import logging
import os

from temporalio import activity

from opentlawpy.config import MAX_COMMAND_OUTPUT_BYTES, MAX_COMMAND_TIMEOUT, WORKSPACE_DIR
from opentlawpy.models.tool_activities import BashCommandInput, BashCommandOutput

logger = logging.getLogger(__name__)


@activity.defn(name="execute_bash_command")
async def execute_bash_command(input: BashCommandInput) -> BashCommandOutput:
    timeout = min(input.timeout, MAX_COMMAND_TIMEOUT)
    cwd = os.path.abspath(WORKSPACE_DIR)
    os.makedirs(cwd, exist_ok=True)

    logger.info("Executing command in %s (timeout=%ds): %s", cwd, timeout, input.command)

    try:
        process = await asyncio.create_subprocess_shell(
            input.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        stdout = stdout_bytes[:MAX_COMMAND_OUTPUT_BYTES].decode(errors="replace")
        stderr = stderr_bytes[:MAX_COMMAND_OUTPUT_BYTES].decode(errors="replace")
        exit_code = process.returncode or 0

        return BashCommandOutput(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            success=exit_code == 0,
        )

    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return BashCommandOutput(
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            exit_code=-1,
            success=False,
        )
    except Exception as e:
        return BashCommandOutput(
            stdout="",
            stderr=str(e),
            exit_code=-1,
            success=False,
        )
