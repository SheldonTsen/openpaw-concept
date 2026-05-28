from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from openpaw.config import TEMPORAL_DEFAULT_RETRIES, TEMPORAL_DEFAULT_TIMEOUT
from openpaw.models.bash_command import BashCommandInput, BashCommandOutput


async def run_bash(command: str, timeout: int = 30) -> str:
    output: BashCommandOutput = await workflow.execute_activity(
        "execute_bash_command",
        arg=BashCommandInput(command=command, timeout=timeout),
        result_type=BashCommandOutput,
        start_to_close_timeout=timedelta(seconds=TEMPORAL_DEFAULT_TIMEOUT + 30),  # arbitrary buffer
        retry_policy=RetryPolicy(maximum_attempts=TEMPORAL_DEFAULT_RETRIES),
    )
    return output.stdout or "(no output)"
