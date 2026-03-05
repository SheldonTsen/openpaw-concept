import shlex

from opentlawpy.tool_handlers._run_bash import run_bash


async def handle(args: dict) -> str:
    command = f"python3 -c {shlex.quote(args['code'])}"
    return await run_bash(
        command=command,
        timeout=args.get("timeout", 30),
    )
