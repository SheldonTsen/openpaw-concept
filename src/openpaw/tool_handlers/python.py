import logging
import shlex

from openpaw.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    command = f"python3 -c {shlex.quote(args['code'])}"
    logger.info(f"Calling python with command: {command}")
    return await run_bash(
        command=command,
        timeout=args.get("timeout", 30),
    )
