import asyncio
import errno
import logging
import os

from temporalio import activity
from temporalio.exceptions import ApplicationError

from openpaw.config import MAX_COMMAND_OUTPUT_BYTES, MAX_COMMAND_TIMEOUT, WORKSPACE_DIR
from openpaw.models.bash_command import BashCommandInput, BashCommandOutput

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

        if exit_code != 0:
            raise ApplicationError(
                stderr or stdout or f"exited with code {exit_code}",
                non_retryable=True,
            )
        return BashCommandOutput(stdout=stdout, stderr=stderr, exit_code=exit_code, success=True)

    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise ApplicationError(
            f"Command timed out after {timeout}s",
            non_retryable=True,
        )
    except OSError as e:
        _TRANSIENT_ERRNOS = {errno.EAGAIN, errno.ENOMEM, errno.EMFILE, errno.ENFILE}
        non_retryable = e.errno not in _TRANSIENT_ERRNOS
        raise ApplicationError(str(e), non_retryable=non_retryable) from e
    except Exception as e:
        raise ApplicationError(str(e), non_retryable=True) from e
