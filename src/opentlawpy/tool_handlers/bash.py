from opentlawpy.tool_handlers._run_bash import run_bash


async def handle(args: dict) -> str:
    return await run_bash(
        command=args["command"],
        timeout=args.get("timeout", 30),
    )
