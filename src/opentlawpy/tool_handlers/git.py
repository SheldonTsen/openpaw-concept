from opentlawpy.tool_handlers._run_bash import run_bash


async def handle(args: dict) -> str:
    command = f"git {args['command']}"
    return await run_bash(
        command=command,
        timeout=args.get("timeout", 30),
    )
