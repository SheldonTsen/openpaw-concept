import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from opentlawpy.models.file_operations import ReadFileInput, ReadFileOutput

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    logger.info("Calling read_file_activity.")
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
