# Sub-Agent Workflow Approaches

## Problem

The main `AgentWorkflow` has a single conversation history that grows with every tool call and LLM interaction. For complex multi-step tasks, the context gets polluted with intermediate tool results, causing the LLM to lose track of the bigger picture.

**Goal**: Keep the orchestrator's context clean by delegating self-contained tasks to sub-agents that run independently, finish, and report back a summary.

---

## Current Architecture (For Context)

```
WhatsApp message
    → AgentWorkflow.new_message signal
    → _thinking_loop (LLM + tools, up to 20 iterations)
    → send WhatsApp reply
```

The thinking loop is a flat loop: call LLM, execute tools, feed results back, repeat. Everything lives in one `_conversation_history`. A 10-tool-call task adds ~20 messages (10 assistant + 10 tool results) to the history that the orchestrator then carries forever.

---

## Approach A: `delegate_task` as a Tool

The LLM sees `delegate_task` alongside bash, read_file, etc. It decides when to delegate.

### How It Works

1. LLM calls `delegate_task(task="Analyze all Python files for security issues")`
2. The tool handler starts a `SubAgentWorkflow` as a **Temporal child workflow**
3. `SubAgentWorkflow` runs its own thinking loop with its own conversation history
4. When done, it returns a result string (the sub-agent's final answer)
5. That result string is fed back to the orchestrator as the tool result
6. Orchestrator sees: `"Found 3 issues: SQL injection in db.py:42, ..."` — not 15 intermediate tool calls

### What the Orchestrator Sees

```
User: "Analyze this codebase for security issues and write a report"
Assistant: [calls delegate_task("Analyze all Python files for security issues")]
Tool result: "Found 3 security issues:\n1. SQL injection in db.py:42\n2. ..."
Assistant: [calls delegate_task("Write a security report based on these findings: ...")]
Tool result: "# Security Report\n\n## Executive Summary\n..."
Assistant: "Here's the security report I prepared: ..."
```

The orchestrator's history stays clean — it never sees the 30+ tool calls the sub-agents made internally.

### Implementation Sketch

**New workflow** (`src/openpaw/workflows/sub_agent_workflow.py`):

```python
@workflow.defn
class SubAgentWorkflow:
    def __init__(self) -> None:
        self._conversation_history: list[dict] = []
        self._tool_definitions: list[ToolDefinition] = []
        self._tool_defs_for_llm: list[dict] = []

    @workflow.run
    async def run(self, input: SubAgentInput) -> str:
        # Load tools (same as parent)
        self._tool_definitions = await workflow.execute_activity(
            load_tools_activity,
            start_to_close_timeout=timedelta(seconds=10),
        )
        self._tool_defs_for_llm = [t.to_llm_format() for t in self._tool_definitions]

        # Seed with the task as the user message
        self._conversation_history.append({
            "role": "user",
            "content": input.task,
        })

        # Run thinking loop (same structure as AgentWorkflow._thinking_loop)
        await self._thinking_loop(system_prompt=input.system_prompt)

        # Return the final assistant message
        return self._conversation_history[-1]["content"]
```

**New tool handler** (`src/openpaw/tool_handlers/delegate_task.py`):

```python
async def handle(args: dict) -> str:
    result: str = await workflow.execute_child_workflow(
        SubAgentWorkflow.run,
        arg=SubAgentInput(
            task=args["task"],
            system_prompt=args.get("system_prompt", DEFAULT_SUB_AGENT_PROMPT),
        ),
        id=f"sub-{workflow.info().workflow_id}-{uuid4().hex[:8]}",
        parent_close_policy=ParentClosePolicy.TERMINATE,
    )
    return result
```

**New TOOL.md** (`src/openpaw/tools/delegate_task/TOOL.md`):

```yaml
---
name: delegate_task
description: Delegate a self-contained task to a sub-agent that runs independently
parameters:
  type: object
  properties:
    task:
      type: string
      description: Clear description of the task for the sub-agent to complete
  required:
    - task
metadata:
  type: workflow
  tier: essential
  priority: 5
---
# Task Delegation

Spawn a sub-agent to handle a self-contained task. The sub-agent has
access to all the same tools (bash, read_file, etc.) and runs its own
thinking loop. It returns a summary of results — you never see the
intermediate steps.

## When to Use

- Complex multi-step tasks (analyze codebase, write report)
- Tasks that would pollute your context with many tool calls
- Parallelizable work (delegate multiple tasks at once)

## When NOT to Use

- Simple one-tool-call tasks (just call the tool directly)
- Tasks that need context from the current conversation
  (the sub-agent starts fresh — it only sees the task description)

## Examples

Delegate analysis:
  task: "Read all .py files in src/ and list any functions longer than 50 lines"

Delegate with specifics:
  task: "Install pandas, load data.csv, compute the mean of the 'revenue' column, and return the result"
```

### Pros

- Cleanest from the orchestrator's perspective — delegation is just another tool call
- LLM decides when to delegate vs. when to use tools directly (it can learn the tradeoff)
- Parallel delegation works naturally (LLM calls `delegate_task` multiple times in one response, `asyncio.gather` runs them concurrently)
- No changes to `AgentWorkflow` itself (besides registering the new workflow in the worker)

### Cons

- `delegate_task` runs inside `_dispatch`, which is called from the workflow — but `workflow.execute_child_workflow` is a workflow API, not an activity API. **This is the main complication.** The tool handler pattern uses `importlib` inside the workflow, so it has access to `workflow.*` APIs, but it would need restructuring to use `workflow.execute_child_workflow` (currently handlers return strings, they'd need to be workflow-aware).
- Sub-agent has no conversation context from the parent. The task description must be fully self-contained.
- Sub-agent's LLM calls cost tokens independently (no shared context).

### The `_dispatch` Problem

Currently `_dispatch` returns a string. To delegate, we'd need it to call `workflow.execute_child_workflow`, which is fine since `_dispatch` already runs in workflow context. But the handler pattern (`mod.handle(args)`) would need to know it's in a workflow context.

**Fix**: Since `_dispatch` already runs inside the workflow and has access to `workflow.*`, and handlers are imported with `workflow.unsafe.imports_passed_through()`, the handler can simply call `workflow.execute_child_workflow` directly. The handler pattern doesn't restrict what you call — it just expects `async def handle(args) -> str`.

---

## Approach B: Explicit `_delegate` Method on AgentWorkflow

Instead of a tool, the orchestrator LLM gets a **two-phase system prompt**: first decide what to do, then delegate or act.

### How It Works

1. LLM's first response is a "plan" (JSON with tasks to delegate and tasks to do directly)
2. `AgentWorkflow` parses the plan, starts child workflows for delegated tasks, and runs tools for direct tasks
3. Results are collected and fed back to the LLM for the final response

### Pros

- More structured — orchestrator always plans before acting
- Can enforce delegation policies (e.g., "always delegate tasks with >3 steps")

### Cons

- Requires a planning prompt that changes the LLM interaction pattern
- More complex to implement — need plan parsing, task routing, result merging
- Harder to iterate on — the plan format is a contract between the prompt and the code
- Less flexible — the LLM can't dynamically decide to delegate mid-conversation

**Verdict**: Overengineered for now. Approach A is simpler and more flexible.

---

## Approach C: Activity-Based Sub-Agent (No Child Workflow)

Instead of a Temporal child workflow, run the sub-agent loop inside a long-running activity.

### How It Works

1. `delegate_task` tool handler calls an activity `run_sub_agent_activity`
2. The activity runs its own LLM loop (call LLM, execute tools, repeat)
3. Returns the final result string

### Pros

- Simpler — no new workflow type, just a new activity
- Fits naturally into existing tool handler pattern

### Cons

- **Loses Temporal guarantees**: If the activity crashes mid-loop, all progress is lost. No replay.
- Activity timeout becomes tricky — sub-agent might need 5 minutes (many LLM calls), but activity timeouts are usually shorter.
- No visibility in Temporal UI — the sub-agent's work is invisible (just a long-running activity).
- Heartbeat timeout required for long activities — adds complexity.

**Verdict**: Tempting for simplicity, but gives up too much. The whole point of Temporal is workflow-level guarantees. If the sub-agent does 8 tool calls and crashes on the 9th, it should be able to replay from the 8th, not start over.

---

## Recommendation: Approach A (`delegate_task` Tool)

Approach A is the right tradeoff:
- Minimal changes to existing code
- LLM learns when to delegate naturally
- Temporal child workflows give us replay, visibility, and fault tolerance
- Parallel delegation works out of the box

---

## Open Questions

### 1. Heartbeat

**Current**: `HeartbeatWorkflow` pokes `AgentWorkflow` every N minutes with `[HEARTBEAT]`.

**With sub-agents**: The heartbeat should only poke the orchestrator. Sub-agents are short-lived (task-scoped) — they start, do work, and return. No idle waiting, no need for heartbeat.

**No changes needed**: HeartbeatWorkflow already targets a specific `chat_id`. Sub-agent workflows have different IDs (`sub-{parent_id}-{uuid}`), so heartbeat won't accidentally poke them.

### 2. Sub-Agent Context

The sub-agent starts with a blank conversation history and only sees the task description. If the task requires context from the parent conversation (e.g., "summarize what the user asked earlier"), the orchestrator must include that context in the task string.

This is a feature, not a bug — it forces clean task boundaries. But it means the orchestrator LLM needs to be good at writing self-contained task descriptions. The system prompt should guide this.

### 3. Sub-Agent System Prompt

The sub-agent needs a different system prompt than the orchestrator:

```python
DEFAULT_SUB_AGENT_PROMPT = """You are a sub-agent executing a specific task.
Complete the task thoroughly and return a clear, concise summary of your results.
Do not ask questions — work with what you have.
If you cannot complete the task, explain what went wrong and what you tried."""
```

The orchestrator's system prompt stays the same, plus it gets the `delegate_task` tool documentation explaining when to delegate.

### 4. Sub-Agent Timeout

Sub-agents should have a max duration (e.g., 5 minutes / 10 iterations). If the sub-agent hits the limit, it returns whatever partial results it has. The orchestrator can then decide to retry, adjust the task, or give up.

Config:
```python
SUB_AGENT_MAX_ITERATIONS = 10
SUB_AGENT_TIMEOUT_MINUTES = 5
```

### 5. Sub-Agent Tool Access

Both orchestrator and sub-agents have the same tools. This is intentional — sometimes a task that seems worth delegating turns out to need just one tool call, and vice versa. The LLM learns the tradeoff.

Should sub-agents be able to delegate to sub-sub-agents? **No** — at least not initially. Cap delegation depth at 1 to avoid runaway recursion. Enforce this by not including `delegate_task` in the sub-agent's tool set.

### 6. Parallel Delegation

The LLM can call `delegate_task` multiple times in one response. Since `_dispatch` already uses `asyncio.gather`, multiple sub-agents run concurrently for free:

```
LLM response:
  tool_call_1: delegate_task("Analyze src/ for bugs")
  tool_call_2: delegate_task("Analyze tests/ for coverage gaps")
  tool_call_3: delegate_task("Check dependencies for vulnerabilities")

→ 3 SubAgentWorkflows start concurrently
→ Results collected in parallel
→ All 3 results fed back to LLM in one step
```

### 7. Cost

Each sub-agent makes its own LLM calls. A task delegated to a sub-agent that takes 5 iterations = 5 LLM calls. The orchestrator pays 1 tool call. Total: 6 LLM calls instead of 5 (the extra 1 is the orchestrator's delegation overhead).

The cost tradeoff: slightly more LLM calls, but the orchestrator's context stays small, so each of its calls is cheaper (fewer input tokens). For long conversations this is a net win.

### 8. State Persistence

Sub-agents are ephemeral — they don't persist state. Their conversation history is discarded after the task completes. Only the result string survives (in the orchestrator's history).

If debugging is needed, Temporal UI shows the full child workflow event history, including every LLM call and tool result. Nothing is truly lost.

### 9. Compaction

Sub-agents don't need compaction — they're short-lived. The orchestrator still compacts as before, and delegation results are just tool result strings in its history.

---

## Code Sharing: Duplication Over Abstraction

The only substantial shared code between `AgentWorkflow` and `SubAgentWorkflow` is `_thinking_loop()` (~70 lines). The `run()` methods are completely different — AgentWorkflow has heartbeat, signals, state persistence, compaction, WhatsApp send; SubAgentWorkflow just loads tools, seeds history, runs the loop, and returns.

**Decision: duplicate the thinking loop.** Reasons:

- The sub-agent loop will likely diverge — different system prompt construction, different max iterations, filtered tool set (no `delegate_task`), different error handling (return partial results vs. append error message). We don't know the details yet.
- Extracting a shared function now means adding parameters and conditionals later to handle differences — worse than two simple copies.
- `_dispatch()` is already module-level (shared), so the gnarly tool dispatch part isn't duplicated.
- 70 lines, not 700. Maintenance cost of duplication is low.
- **Escape hatch**: If after implementation the loops stay identical, extracting to a shared function is a trivial refactor (move the loop out, pass state as args). Going the other direction — un-sharing a premature abstraction — is harder.

Inheritance was considered and rejected: Temporal's `@workflow.defn` / `@workflow.run` decorators add constraints, and building a class hierarchy for one shared method adds coupling without benefit.

---

## Implementation Order

1. **`SubAgentInput` model** — `models/sub_agent.py` (task string + optional system prompt)
2. **`SubAgentWorkflow`** — `workflows/sub_agent_workflow.py` (duplicate thinking loop from AgentWorkflow, strip out what's not needed)
3. **`delegate_task` TOOL.md** — `tools/delegate_task/TOOL.md`
4. **`delegate_task` handler** — `tool_handlers/delegate_task.py`
5. **Register `SubAgentWorkflow`** in `worker/__main__.py`
6. **Config** — `SUB_AGENT_MAX_ITERATIONS`, `SUB_AGENT_TIMEOUT_MINUTES`
7. **Tests** — Sub-agent completes task, returns result; orchestrator delegates and receives result; parallel delegation; sub-agent timeout
