import asyncio
import logging
from datetime import timedelta

from temporalio import workflow

from openpaw.config import APPROVAL_COMMAND_PREVIEW_LENGTH
from openpaw.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_MINUTES = 5


async def handle(args: dict, *, workflow_ref=None) -> str:
    command = args["command"]
    timeout = args.get("timeout", 30)

    if workflow_ref is None or not hasattr(workflow_ref, "_awaiting_approval"):
        return (
            "Error: bash_with_approval requires user approval which is not "
            "available in this context."
        )

    # --- Approval gate ---

    args_summary = command[:APPROVAL_COMMAND_PREVIEW_LENGTH]
    await workflow_ref._send_status(
        f"Approval needed for bash command:\n`{args_summary}`\nReply YES to approve or NO to deny."
    )

    workflow_ref._awaiting_approval = True
    workflow_ref._approval_response = None

    try:
        await workflow.wait_condition(
            lambda: workflow_ref._approval_response is not None,
            timeout=timedelta(minutes=APPROVAL_TIMEOUT_MINUTES),
        )
    except asyncio.TimeoutError:
        workflow_ref._awaiting_approval = False
        return "Error: Approval timed out. Command was not executed."

    approved = workflow_ref._approval_response
    workflow_ref._awaiting_approval = False
    workflow_ref._approval_response = None

    if not approved:
        return "Error: User denied the command."

    return await run_bash(command=command, timeout=timeout)
