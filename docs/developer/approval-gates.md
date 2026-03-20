# Approval Gates — Implementation Design

## Problem

The agent can execute any tool the LLM chooses. Some actions are dangerous — deleting files, running destructive bash commands, writing to sensitive paths. We want human approval before certain tool calls execute.

## Concrete example: `bash_with_approval`

We'll build a new tool called `bash_with_approval` that works exactly like `bash`, except it pauses and asks the user for permission before executing. This demonstrates the signal gate pattern without modifying the existing `bash` tool.

The LLM sees both tools and can choose which to use — or you can replace `bash` entirely with `bash_with_approval` for untrusted users by swapping TOOL.md files.

## How tool handlers work today

```
LLM returns tool_calls
  → _dispatch(tool_call) resolves name via importlib
  → openpaw.tool_handlers.bash.handle(args)
  → calls workflow.execute_activity("execute_bash_command", ...)
  → result string fed back to LLM
```

Tool handlers already run inside the workflow context. Look at `delegate_task.py` — it calls `workflow.execute_child_workflow()` directly. This means a tool handler can also call `workflow.wait_condition()`. That's our entry point.

## What needs to change

### 1. Add approval signal to AgentWorkflow

The workflow needs a way to receive YES/NO responses. Add a signal and a flag:

```python
# agent_workflow.py

@workflow.defn
class AgentWorkflow:
    def __init__(self) -> None:
        # ... existing fields ...
        self._approval_response: bool | None = None
        self._awaiting_approval: bool = False
```

Two options for how the signal arrives:

**Option A: Separate signal** — add `approval_response` signal, listener routes YES/NO to it. Problem: listener needs to know if an approval is pending, coupling it to workflow state.

**Option B: Intercept in `new_message` (simpler)** — all messages come through `new_message` as today. When `_awaiting_approval` is True, YES/NO messages are routed to `_approval_response` instead of `_pending_messages`:

```python
@workflow.signal
def new_message(self, text: str) -> None:
    if self._awaiting_approval and text.strip().upper() in ("YES", "NO"):
        self._approval_response = text.strip().upper() == "YES"
    else:
        self._pending_messages.append(IncomingMessage(text=text))
```

This keeps the listener completely unchanged. The workflow handles routing internally.

### 2. Expose the approval state

The tool handler needs to access and mutate `_approval_response` and `_awaiting_approval`. Since `_dispatch` (and therefore `handle()`) runs inside the workflow context but doesn't have a reference to `self`, we need a way to bridge this.

**Simplest approach**: move `_dispatch` into `AgentWorkflow` as a method. It already runs inside the workflow — making it a method is a small refactor:

```python
# agent_workflow.py

class AgentWorkflow:
    # ...

    async def _dispatch(self, tool_call: dict) -> str:
        func = tool_call["function"]
        name = func["name"]
        args = func["arguments"]

        try:
            with workflow.unsafe.imports_passed_through():
                mod = importlib.import_module(f"openpaw.tool_handlers.{name}")
        except ModuleNotFoundError:
            return f"Error: Unknown tool '{name}'"

        return await mod.handle(args, workflow_ref=self)
```

Note `workflow_ref=self` — the handler gets a reference to the workflow instance. Existing handlers ignore it (they accept `**kwargs` or we add it as optional).

### 3. Create the tool handler

`src/openpaw/tool_handlers/bash_with_approval.py`:

```python
import asyncio
import logging
from datetime import timedelta

from temporalio import workflow

from openpaw.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_MINUTES = 5


async def handle(args: dict, workflow_ref=None) -> str:
    command = args["command"]
    timeout = args.get("timeout", 30)

    if workflow_ref is None:
        # Fallback: no approval gate (e.g. called from sub-agent)
        return await run_bash(command=command, timeout=timeout)

    # --- Approval gate ---

    # Send the approval request to the user
    args_summary = command[:200]
    await workflow_ref._send_status(
        f"⚠️ Approval needed for bash command:\n"
        f"`{args_summary}`\n"
        f"Reply YES to approve or NO to deny."
    )

    # Set the flag and wait for the user's response
    workflow_ref._awaiting_approval = True
    workflow_ref._approval_response = None

    try:
        await workflow.wait_condition(
            lambda: workflow_ref._approval_response is not None,
            timeout=timedelta(minutes=APPROVAL_TIMEOUT_MINUTES),
        )
    except asyncio.TimeoutError:
        workflow_ref._awaiting_approval = False
        await workflow_ref._send_status("⏰ Approval timed out. Command denied.")
        return "Error: Approval timed out. Command was not executed."

    approved = workflow_ref._approval_response
    workflow_ref._awaiting_approval = False
    workflow_ref._approval_response = None

    if not approved:
        await workflow_ref._send_status("❌ Command denied.")
        return "Error: User denied the command."

    await workflow_ref._send_status("✅ Approved. Executing...")
    return await run_bash(command=command, timeout=timeout)
```

The handler:
1. Sends a status message showing the command
2. Sets `_awaiting_approval = True` so `new_message` intercepts YES/NO
3. Waits via `workflow.wait_condition` (Temporal keeps the workflow alive, no resources consumed)
4. On YES → runs the command. On NO or timeout → returns error string to the LLM.

### 4. Create the TOOL.md

`src/openpaw/tools/bash_with_approval/TOOL.md`:

```yaml
---
name: bash_with_approval
description: Execute bash commands with human approval required before execution
parameters:
  type: object
  properties:
    command:
      type: string
      description: The bash command to execute (requires user approval)
    timeout:
      type: integer
      description: Optional timeout in seconds (default 30, max 300)
      default: 30
  required:
    - command
metadata:
  type: cli
  activity: execute_bash_command
  tier: essential
  priority: 2
---

# Bash Command Execution (With Approval)

Execute shell commands with human-in-the-loop approval. The user will be
asked to approve or deny each command before it runs.

Use this tool for any bash commands. The user will see the command and
can reply YES or NO.
```

### 5. Update existing handler signature

Existing handlers need to accept the optional `workflow_ref` without breaking. Two options:

**Option A: Add `**kwargs`** to all handlers (minimal change):

```python
# tool_handlers/bash.py
async def handle(args: dict, **kwargs) -> str:
    return await run_bash(command=args["command"], timeout=args.get("timeout", 30))
```

**Option B: Add `workflow_ref=None`** explicitly to handlers that might use it, `**kwargs` to the rest.

Option A is less invasive — existing handlers just ignore the extra kwarg.

## Flow walkthrough

```
1. User: "Delete all .tmp files in the workspace"

2. LLM decides: bash_with_approval(command="rm *.tmp")

3. _dispatch → tool_handlers/bash_with_approval.handle(args, workflow_ref=self)

4. Handler sends: "⚠️ Approval needed for bash command: `rm *.tmp`
                    Reply YES to approve or NO to deny."

5. Workflow pauses at wait_condition (no resources consumed)

6. User replies: "YES"
   → new_message signal fires
   → _awaiting_approval is True, text is "YES"
   → sets _approval_response = True

7. wait_condition unblocks

8. Handler runs: run_bash(command="rm *.tmp")

9. Result fed back to LLM: "Deleted 3 files"

10. LLM responds to user: "Done — removed 3 .tmp files."
```

If the user replies "NO" at step 6, the handler returns `"Error: User denied the command."` and the LLM adapts (e.g. "OK, I won't delete those files.").

## What about parallel tool calls?

If the LLM calls `bash_with_approval` alongside other tools in the same response:

```python
tasks = [self._dispatch(tool_call=tc) for tc in llm_output.tool_calls]
tool_results = await asyncio.gather(*tasks, return_exceptions=True)
```

The non-approval tools run immediately. The `bash_with_approval` call blocks at `wait_condition` while the others complete. `asyncio.gather` waits for all of them, so the overall batch completes when the approval comes through (or times out).

One edge case: if the LLM calls `bash_with_approval` twice in the same batch, both handlers would race for the same `_approval_response` field. This is unlikely (the LLM rarely calls the same tool twice), but if needed, the fix is to give each approval request a unique ID and match responses.

## Temporal safety

- **Replay-safe**: `workflow.wait_condition` is a Temporal primitive. If the worker crashes mid-wait, the workflow replays from event history. The approval signal is in the history, so the handler picks up where it left off.
- **Deterministic**: The handler only uses Temporal APIs (`workflow.wait_condition`, `workflow.execute_activity`). No randomness, no system calls, no clock reads.
- **No external state**: Everything lives in the workflow's event history. No database, no Redis, no shared memory.

## Implementation order

1. Add `_approval_response` and `_awaiting_approval` fields to `AgentWorkflow.__init__`
2. Update `new_message` signal to intercept YES/NO when `_awaiting_approval`
3. Move `_dispatch` into `AgentWorkflow` as a method, pass `workflow_ref=self`
4. Add `**kwargs` to existing handler `handle()` signatures
5. Create `tools/bash_with_approval/TOOL.md`
6. Create `tool_handlers/bash_with_approval.py`
7. Tests:
   - Approval granted → command runs, result returned
   - Approval denied → error string returned, command not run
   - Timeout → error string returned
   - Regular `bash` tool still works unchanged (no approval gate)

## Future extensions

- **Per-user tool sets**: Untrusted users get `bash_with_approval` instead of `bash`. Trusted users get `bash` directly. Driven by `AgentWorkflowInput` or a user permissions config.
- **Approval for other tools**: Same pattern works for `write_file_with_approval`, `python_with_approval`, etc. The `_run_bash.py` shared helper pattern means the actual execution logic is reused.
- **Batch approval**: "The agent wants to run 3 commands: ... Approve all?" — single YES/NO for the batch.
