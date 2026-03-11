import logging

from opentlawpy.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    command = f"git {args['command']}"
    logger.info(f"Calling git with {command}")
    return await run_bash(
        command=command,
        timeout=args.get("timeout", 30),
    )
