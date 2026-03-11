import logging
import shlex

from opentlawpy.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    parts = ["grep"]
    if not args.get("case_sensitive", False):
        parts.append("-i")
    if args.get("recursive", True):
        parts.append("-rn")
    parts.append(shlex.quote(args["pattern"]))
    parts.append(shlex.quote(args.get("path", ".")))
    command = " ".join(parts)
    logger.info(f"Calling grep with command: {command}")
    return await run_bash(
        command=command,
        timeout=args.get("timeout", 30),
    )
