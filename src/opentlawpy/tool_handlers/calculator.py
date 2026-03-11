import logging
import shlex

from opentlawpy.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    expr = args["expression"]
    command = f"python3 -c {shlex.quote(f'print({expr})')}"
    logger.info(f"Calling calculator with command: {command}")
    return await run_bash(
        command=command,
        timeout=args.get("timeout", 30),
    )
