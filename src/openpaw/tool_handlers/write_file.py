import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from openpaw.models.file_operations import WriteFileInput, WriteFileOutput

logger = logging.getLogger(__name__)


async def handle(args: dict, **kwargs) -> str:
    logger.info("Calling write_file.")
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
