# Architecture Decision Records

Key decisions made during development. Each records what was decided, why, and what alternatives were rejected.

---

## ADR-000: Temporal as Orchestration Layer

**Context**: Building an agentic system that calls LLMs, executes tools, manages state, and needs to be resilient to crashes mid-task. Need to decide how to orchestrate the agent loop.

**Decision**: Use Temporal for workflow orchestration. The agent thinking loop (LLM call → tool execution → repeat) is a Temporal workflow. Each tool/LLM call is a Temporal activity.

**Why**:
- **Fault tolerance for free**: If the worker crashes mid-tool-call, Temporal replays the workflow from the last checkpoint. No manual state recovery code.
- **Activity routing across machines**: Activities can run on different workers on different machines. This is why the WhatsApp send activity runs on the listener container while LLM calls run on the worker container — Temporal routes each activity to the right place via task queues.
- **Full visibility**: Every LLM call, tool execution, and signal is recorded in Temporal's event history. The UI shows exactly what happened and when. No custom logging needed for debugging.
- **Signals for real-time input**: New messages arrive as signals to a running workflow. No polling, no message queues to manage.
- **Child workflows**: Sub-agent delegation maps directly to Temporal child workflows — gets replay, visibility, and parent-child lifecycle management.
- **Timeouts and retries are declarative**: `start_to_close_timeout`, `RetryPolicy`, `execution_timeout` — all built in, not hand-rolled.

**Alternatives rejected**:
- Plain async Python (no orchestrator): Works for simple cases but loses all state on crash. Must build retry logic, timeout handling, and state persistence manually.
- Celery/Redis queue: Good for simple task queues but no workflow concept — can't express "call LLM, then based on result call these tools, then call LLM again" as a durable workflow.
- LangGraph/LangChain: Higher-level agent frameworks but less control, no built-in persistence across process restarts, weaker observability.

**Trade-off**: Temporal adds infrastructure (server + database) and learning curve. Worth it because the agent loop is inherently stateful and long-running — exactly what Temporal is designed for.

---

## ADR-001: Two-Container Architecture (Worker + Listener)

**Context**: neonize (WhatsApp Go FFI) is blocking and needs its own event loop. The Temporal worker needs its own async loop.

**Decision**: Two containers — `worker` (workflows + most activities) and `whatsapp-listener` (neonize + `send_whatsapp_message` activity). Both poll the same Temporal namespace but different task queues (`agent-tasks` vs `whatsapp-tasks`).

**Why**: neonize's `connect()` blocks the main thread (Go runtime). Running it alongside Temporal workflows in one process requires a daemon thread for the async worker. Splitting into two containers keeps each process simple. The `send_whatsapp_message` activity must run where the neonize client lives, so it gets its own task queue.

**Alternatives rejected**:
- Single container with threading: Works but fragile — neonize Go runtime swallows signals, makes shutdown messy
- Separate send queue unnecessary: Without it, the worker container would need neonize installed and a WhatsApp session

See `docs/task-queues.md` for routing details.

---

## ADR-002: Tool Handler Pattern (importlib Convention)

**Context**: LLM returns tool calls by name. Need to dispatch `"bash"` to the right handler code.

**Decision**: Convention-based dispatch using `importlib.import_module(f"opentlawpy.tool_handlers.{name}")`. Each tool has a module in `tool_handlers/` with an `async def handle(args: dict) -> str` function. Tool definitions live in `tools/{name}/TOOL.md` with YAML frontmatter.

**Why**: Zero registration boilerplate. Adding a new tool = create TOOL.md + create handler module. The loader discovers tools via glob, the dispatcher discovers handlers via importlib. No central registry to maintain.

**Alternatives rejected**:
- Central registry dict: Requires manual registration, easy to forget
- Decorator-based registration: More magic, harder to grep for

**Consequence**: Handler filenames must match tool names exactly. Tests enforce this (`test_every_tool_has_handler`).

---

## ADR-003: TOOL.md with YAML Frontmatter

**Context**: Tools need structured metadata (name, parameters, tier, priority) for the LLM and human-readable documentation for the system prompt.

**Decision**: Each tool has a `TOOL.md` file with YAML frontmatter (structured data) and a markdown body (documentation). The frontmatter drives LLM tool definitions. The body is appended to the system prompt as tool documentation.

**Why**: Single source of truth per tool. The LLM sees both the structured schema (for function calling) and the prose documentation (for understanding when/how to use tools).

**Trade-off**: Tool docs count as input tokens on every LLM call — roughly doubled since both the JSON schema and the markdown body are sent. Acceptable for now but may need filtering for local LLMs with small context windows.

---

## ADR-004: Tier-Based Tool Filtering

**Context**: Not all tools should be loaded for every interaction. Local LLMs with small context windows need fewer tools.

**Decision**: Tools have a `tier` in their metadata: `essential`, `common`, `specialized`, `experimental`. Default load is `essential` + `common`. Configurable via `load_tools(include_tiers=[...])`.

**Why**: Keeps the default tool set small. Essential tools (bash, python, delegate_task) are always available. Common tools (git, grep, etc.) add utility without bloating context too much.

**Not yet done**: No env var to control tiers at runtime. `load_tools_activity` uses hardcoded defaults. Future work to make this configurable via `config.py`.

---

## ADR-005: Sub-Agent as Tool (`delegate_task`)

**Context**: Complex tasks pollute the orchestrator's context with intermediate tool results. Need a way to offload self-contained work.

**Decision**: `delegate_task` is a regular tool. The LLM decides when to delegate. The handler starts a `SubAgentWorkflow` as a Temporal child workflow, blocks until it completes, and returns the result string.

**Why**:
- Minimal changes to existing code — delegation is just another tool call
- LLM learns the delegation tradeoff naturally
- Parallel delegation works for free via `asyncio.gather`
- Child workflow gives Temporal guarantees (replay, visibility, fault tolerance)
- `ParentClosePolicy.TERMINATE` ensures orphan cleanup

**Alternatives rejected**:
- Explicit planning phase (Approach B): Overengineered, requires plan parsing, less flexible
- Activity-based sub-agent (Approach C): Loses Temporal replay guarantees, no visibility in UI
- Shared thinking loop: Loops will likely diverge, premature abstraction

**Consequences**:
- Sub-agents filter out `delegate_task` from their tools (no recursion)
- Sub-agents are ephemeral — no state persistence, no heartbeat, no compaction
- Must use `workflow.uuid4()` not `uuid.uuid4()` inside handlers (sandbox restriction)
- Handler catches all exceptions and returns error strings (avoids non-serializable exceptions in `asyncio.gather`)

See `docs/sub-agent-approaches.md` for the full analysis.

---

## ADR-006: Duplicated Thinking Loop (Not Shared)

**Context**: `AgentWorkflow` and `SubAgentWorkflow` both have a `_thinking_loop` (~70 lines). Should this be shared?

**Decision**: Duplicate the loop. Each workflow has its own copy.

**Why**:
- The loops use different config (`MAX_TOOL_ITERATIONS` vs `SUB_AGENT_MAX_ITERATIONS`, `SYSTEM_PROMPT` vs `SUB_AGENT_SYSTEM_PROMPT`)
- Sub-agent filters tools post-load (`delegate_task` excluded)
- Sub-agent has different max-iterations-exceeded behavior (returns partial results vs sends "thinking limit" message)
- Loops will likely diverge further as features are added (orchestrator might get compaction mid-loop, sub-agent won't)
- `_dispatch()` is module-level and shared — the heavy part isn't duplicated
- 70 lines, not 700 — maintenance cost is low

**Escape hatch**: If the loops stay identical after more development, extracting to a shared function is a trivial refactor.

---

## ADR-007: Conversation History as `list[dict]`

**Context**: Need to store conversation history that's compatible with OpenAI/Anthropic chat completion format.

**Decision**: History is `list[dict]` with standard `role`/`content` keys. System prompt is prepended on every LLM call (not stored in history). Persisted as JSON via `save_state_activity`.

**Why**: Direct compatibility with LLM APIs — no translation layer. Simple to serialize. Easy to inspect. Tool results are just dicts with `role: "tool"`.

**Trade-off**: No typed messages — it's dicts all the way. Acceptable because the format is dictated by the LLM API anyway.

---

## ADR-008: State Persistence via JSON Files

**Context**: Conversation history needs to survive workflow restarts (timeout → new workflow for same chat).

**Decision**: JSON file per chat at `data/state/{chat_id}/state.json`. Load on workflow start, save after each reply.

**Why**: Zero dependencies — no database needed. Files are inspectable (`cat state.json`). Volume-mountable for Docker. Adequate for single-user / low-concurrency personal use.

**Alternatives rejected**:
- Database (PostgreSQL/SQLite): Overkill for single-user
- YAML/Markdown state files: Harder to round-trip `list[dict]` with tool calls
- Temporal's own state (continue-as-new): Size limits, not designed for large conversation histories

---

## ADR-009: Simple Compaction (Threshold-Based)

**Context**: Conversation history grows without bound. LLM context windows are finite and cost scales with input tokens.

**Decision**: When history exceeds `COMPACTION_THRESHOLD` (default 50 messages), call an LLM to summarize everything except the last 2 messages. Result: 1 summary + 2 recent = 3 messages.

**Why**: Simple, predictable, good enough. The summary preserves key context while dramatically reducing token count. Using the last 2 messages (not more) keeps the compacted state small.

**Future**: Could add importance scoring, hierarchical summaries, or semantic memory. See `docs/upgrade-ideas.md`.

---

## ADR-010: Separate Interfaces, Shared Workspace

**Context**: Adding a terminal interface alongside WhatsApp. Should they share conversation history?

**Decision**: Interfaces are isolated processes with isolated conversation histories. The workspace filesystem is implicitly shared.

**Why**:
- WhatsApp is for quick asks, terminal is for focused work — different contexts
- Shared conversation history would leak context (small talk polluting coding sessions)
- Artifacts (files, scripts, outputs) are naturally shared via `workspace/`
- Each interface registers its own `send_message` activity on its own task queue
- Simple, no abstraction needed

**Future**: If cross-interface context is needed, options include a shared state file, workspace README, or Temporal history queries. See `docs/upgrade-ideas.md` section 2.

---

## ADR-011: Heartbeat as Abandoned Child Workflow

**Context**: The agent should periodically check in (e.g., check for pending tasks) even when no messages arrive.

**Decision**: `HeartbeatWorkflow` runs as a child workflow with `ParentClosePolicy.ABANDON`. It loops: sleep N minutes → poke the agent via `poke_agent` activity (which signals the `AgentWorkflow`). `continue_as_new` every 100 pokes to bound event history.

**Why**:
- `ABANDON` policy means the heartbeat survives parent workflow restarts (new `AgentWorkflow` starts, old heartbeat keeps running)
- `poke_agent` uses atomic start-or-signal, so it works whether the `AgentWorkflow` is running or needs to be started
- Temporal-native approach — no external cron needed

**Alternative rejected**: Temporal's built-in cron — harder to stop/start dynamically, less flexible for variable intervals.

---

## ADR-012: `workflow.uuid4()` for Determinism

**Context**: Needed unique IDs for child workflow IDs inside workflow code.

**Decision**: Always use `workflow.uuid4()` inside workflows, never `uuid.uuid4()`.

**Why**: Temporal's workflow sandbox blocks `uuid.uuid4()` because it uses OS randomness (non-deterministic). `workflow.uuid4()` is Temporal's seeded alternative that's safe for replay. Using stdlib uuid causes `RestrictedWorkflowAccessError`, which then cascades into JSON serialization failures when the exception hits `asyncio.gather(return_exceptions=True)`.

**Rule**: Any non-deterministic stdlib call inside a workflow must use Temporal's wrapper (`workflow.uuid4()`, `workflow.now()`, `workflow.random()`).
