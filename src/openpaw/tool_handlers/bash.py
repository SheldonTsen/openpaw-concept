import logging

from openpaw.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    logger.info(f"Calling run_bash with command: {args['command']}")
    return await run_bash(
        command=args["command"],
        timeout=args.get("timeout", 30),
    )
