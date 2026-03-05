from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from opentlawpy.models.tool_activities import ReadFileInput, ReadFileOutput


async def handle(args: dict) -> str:
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
