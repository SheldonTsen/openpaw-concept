# Temporal-OpenClaw MVP Implementation - Execution List

**Status**: 🟡 In Progress
**Start Date**: 2026-02-28
**Target MVP**: WhatsApp-integrated agentic system with Temporal orchestration

**Philosophy**: Lean end-to-end first. Get a message flowing through the entire stack (WhatsApp → Temporal → response) before adding LLM logic. This lets us debug the plumbing in isolation.

---

## Phase 0: Project Setup 📚

**Goal**: Project structure, dependencies, git hygiene

### 0.1 Documentation (DONE)
- [x] Create `README.md`
- [x] Create `CLAUDE.md`
- [x] Create `.env.example`

### 0.2 Python Project Setup (DONE)
- [x] Create `pyproject.toml` with uv
- [x] Create `.gitignore`
- [x] Install core dependencies: `temporalio`, `neonize`, `anthropic`

---

## Phase 1: Lean End-to-End ("Hello World") 🔌

**Goal**: WhatsApp message in → Temporal workflow → "Hello World" response back. No LLM, no tools, no state. Just prove the plumbing works.

**What we're building:**
```
You send WhatsApp msg → Neonize listener receives it
  → Listener starts/signals Temporal workflow
  → Workflow runs a simple activity that returns "Hello! I received: <your message>"
  → Workflow calls whatsapp_send_message activity
  → You receive response on WhatsApp
```

### 1.1 Docker Compose + Temporal (DONE)
- [x] Create `docker-compose.yml` (Temporal server + UI + PostgreSQL) — was done in Phase 0
- [x] Create `Dockerfile` (worker image) — `python:3.13-slim` + uv
- [x] Add `agent` service to `docker-compose.yml` (depends on temporal + namespace creation)
- [ ] Verify Temporal UI accessible at localhost:8080
- [ ] Verify worker connects to Temporal

### 1.2 Hello World Workflow + Worker (DONE)
- [x] Create `src/workflows/__init__.py`
- [x] Create `src/workflows/agent_workflow.py` — minimal workflow:
  - Receives signal `new_message(sender, text)`
  - Calls `whatsapp_send_message` activity to reply with `"Hello! I received: {text}"`
  - Waits for next message (loop with `wait_condition`, 60 min timeout)
- [x] Create `src/activities/__init__.py`
- [x] Create `src/activities/whatsapp.py` — factory pattern: `create_send_whatsapp_message_activity(neonize_client)` returns activity bound to neonize client
- [x] Create `src/worker/__init__.py`
- [x] Create `src/worker/worker.py` — `run_worker(client, activities)` + `create_temporal_client(address)`
- [x] Create `src/models/__init__.py`
- [x] Create `src/models/messages.py` — `IncomingMessage`, `SendMessageInput`, `SendMessageOutput`
- [x] Test: 3 workflow tests pass via `WorkflowEnvironment.start_time_skipping()`

### 1.3 WhatsApp Listener (Neonize) (DONE)
- [x] Create `src/whatsapp/__init__.py`
- [x] Create `src/whatsapp/listener.py` — `WhatsAppListener` class:
  - Connects to WhatsApp via Neonize, registers `ConnectedEv`, `MessageEv`, `PairStatusEv` handlers
  - Filters messages by `is_from_me` or `my_phone_number`
  - Atomic start-or-signal via `id_conflict_policy=USE_EXISTING` + `start_signal`
  - Routes messages to Temporal via `asyncio.run_coroutine_threadsafe`
- [x] Create `src/main.py` + `src/__main__.py` — single-process entry point:
  - Main thread: neonize `client.connect()` (blocking Go event loop)
  - Daemon thread: asyncio loop with Temporal Worker + Client
  - Signal handlers with `os._exit(0)` for clean shutdown
- [x] Add `agent` service to `docker-compose.yml` (single service, not separate listener)
- [x] Update `.env.example` with `MY_PHONE_NUMBER`

Follow Up (DONE):
- [x] directories renamed to `src/opentlawpy/`, imports use `from opentlawpy import x`
- [x] Removed `Dockerfile.dev`, `docker-compose.dev.yml` uses `docker compose watch` (`sync+restart`)
- [x] Renamed `my_phone_number` to `my_whatsapp_number` everywhere (matches `MY_WHATSAPP_NUMBER` env var)
- [x] Created `opentlawpy/config.py` — all config in one place (TASK_QUEUE, NAMESPACE, TEMPORAL_ADDRESS, MY_WHATSAPP_NUMBER, NEONIZE_DB_PATH)
- [x] Created `opentlawpy/logging.py` — shared `setup_logging()` function
- [x] Removed duplicate test (`test_workflow_start_signal_pattern` was identical to `test_workflow_echoes_message`)
- [x] Simplified `_get_message_timestamp` — uses `message.Info.Timestamp.seconds` directly (protobuf Timestamp)
- [x] Added `logger.debug()` for skipped old messages and no-text messages

neonize.db note: It stores WhatsApp session auth (encryption keys). Only the listener container mounts it. The worker container never touches WhatsApp — the `send_whatsapp_message` activity runs on the listener's Temporal worker (same task queue, different worker process).



### 1.4 End-to-End Test
- [ ] Start all services: `docker-compose up`
- [ ] Scan QR code to link WhatsApp
- [ ] Send yourself a WhatsApp message
- [ ] Verify you receive "Hello! I received: ..." back
- [ ] Verify workflow visible in Temporal UI (localhost:8080)
- [ ] Send a second message — verify it signals the EXISTING workflow (not a new one)

### 1.5 Dev Workflow Validation (DONE — config created)
- [x] Create `docker-compose.dev.yml` with hot reload (watchdog `auto-restart`)
- [x] Create `Dockerfile.dev` with dev dependencies (watchdog)
- [x] Verify: edit workflow code → worker auto-restarts → no rebuild needed
- [x] Verify: `docker-compose logs -f agent --tail=20` shows reload
- [x] Change "Hello!" to "Hey!" in workflow, confirm change takes effect without rebuild

### 1.6 Automated Tests (DONE)
- [x] Create `tests/test_workflow.py` — 3 tests using `WorkflowEnvironment.start_time_skipping()`:
  - `test_workflow_echoes_message` — signal → echo activity called
  - `test_workflow_start_signal_pattern` — atomic start+signal works
  - `test_workflow_multiple_messages` — handles multiple signals in sequence
- [x] All 3 tests pass

**Phase 1 exit criteria**: You send a WhatsApp message, you get a response back, you can see it in Temporal UI, and code changes hot-reload.

---

## Phase 2: LLM Integration 🤖

**Goal**: Replace "Hello World" with actual LLM calls. Agent can think and respond.

### 2.1 LLM Call Activity (DONE)
- [x] Create `src/opentlawpy/models/llm.py` — `LLMCallInput`, `LLMCallOutput` dataclasses
- [x] Create `src/opentlawpy/llm/__init__.py`
- [x] Create `src/opentlawpy/llm/anthropic_client.py` — async wrapper around Anthropic SDK
- [x] Create `src/opentlawpy/activities/llm_call.py` — factory pattern matching whatsapp.py
- [x] Add `ANTHROPIC_API_KEY` and `LLM_MODEL` to `config.py`
- [x] Register `call_llm` activity in `worker/__main__.py`
- [x] Test: 3 unit tests pass (activity returns response, propagates errors, client maps SDK response)
- [ ] Add retry policy (3 attempts, exponential backoff) — deferred to Phase 6

Addendum:
- [x] Move workflow timeout to config.py (`WORKFLOW_TIMEOUT_MINUTES`, default 15 min)

### 2.2 Agent Thinking Loop (No Tools Yet) (DONE)
- [x] Update `agent_workflow.py`:
  - On message: call LLM activity with conversation history
  - Return LLM's text response via WhatsApp
  - Store conversation history in workflow state (in-memory, not persisted yet)
- [x] Test: send WhatsApp message → get actual LLM response back
- [x] Test: send follow-up message → LLM has context from previous message

Note: `result_type=LLMCallOutput` is required on `execute_activity` when calling by string name — without it Temporal can't deserialize the result and the workflow task retries forever.

Addendum — OpenRouter (free) support:
- [x] Create `src/opentlawpy/llm/openrouter_client.py` — async httpx client for OpenRouter `/v1/chat/completions`
- [x] Add `LLM_PROVIDER` config (default `openrouter`) + `OPENROUTER_API_KEY` to `config.py`
- [x] Widen `create_call_llm_activity` to accept any client with `.chat()` method (duck typing)
- [x] Branch in `create_activities.py` on `LLM_PROVIDER` (`anthropic` vs `openrouter`)
- [x] Pass `OPENROUTER_API_KEY` and `LLM_PROVIDER` through `docker-compose.yaml` + `.env.example`
- [x] Unit tests: 3 tests for OpenRouterClient (request body, missing usage, HTTP error)

Addendum — Local MLX model support:
- [x] Create `src/opentlawpy/llm/openai_client.py` — generic OpenAI-compatible client (works with MLX LM server, vLLM, etc.)
- [x] Add `LOCAL_MODEL_URL` to `config.py` (default `http://localhost:8080/v1`)
- [x] Add `elif LLM_PROVIDER == "local"` branch in `create_activities.py`
- [x] Create `scripts/start-mlx-server.sh` — starts MLX LM server with configurable model/port

### 2.3 System Prompt (DONE)
- [x] Add `SYSTEM_PROMPT` constant to `config.py`
- [x] Workflow prepends system prompt as `{"role": "system", ...}` to every LLM call (not stored in conversation history)
- [x] Test: system prompt is prepended to every LLM call and not duplicated

---

## Phase 3: Tool Execution 🔧

**Goal**: LLM can call tools (bash, read_file, write_file). Multi-step reasoning works.

### 3.1 Tool Definitions (DONE)
- [x] Moved `tools/` → `src/opentlawpy/tools/` (available inside Docker containers)
- [x] 8 TOOL.md files already exist: bash, read_file, write_file, python, web_search, git, grep, calculator
- [x] Created `src/opentlawpy/models/tools.py` — `ToolDefinition` dataclass with `to_llm_format()` (OpenAI function-calling format)
- [x] Created `src/opentlawpy/utils/__init__.py` (empty)
- [x] Created `src/opentlawpy/utils/tool_loader.py` — `load_tools()` parses YAML frontmatter, filters by tier, sorts by priority
- [x] Added `pyyaml>=6.0` to `pyproject.toml` dependencies
- [x] Added `TOOLS_DIR` to `config.py` (resolves to `src/opentlawpy/tools/`)
- [x] Created `tests/test_tool_loader.py` — 5 tests (load all, required fields, filter by tier, sorted by priority, LLM format)
- [x] All 15 tests pass, ruff clean

### 3.2 Tool Activities (DONE)
- [x] Created `src/opentlawpy/models/tool_activities.py` — `BashCommandOutput/Output`, `ReadFileInput/Output`, `WriteFileInput/Output` dataclasses
- [x] Added `WORKSPACE_DIR` to `config.py` (env var with `./workspace` default)
- [x] Created `src/opentlawpy/activities/tool_command.py` — generic `execute_bash_command` activity (`asyncio.create_subprocess_shell`, timeout enforcement, output truncation)
- [x] Created `src/opentlawpy/activities/file_operations.py` — `read_file_activity`, `write_file_activity` with path traversal prevention via `os.path.realpath()` + workspace boundary check
- [x] Updated `create_activities.py` — registers all 3 new activities alongside `call_llm`
- [x] Created `tests/test_tool_command.py` — 3 tests (simple command, nonzero exit, timeout)
- [x] Created `tests/test_file_operations.py` — 8 tests (read/write, path traversal, large file, append, auto-create dirs)
- [x] All 26 tests pass, ruff clean

### 3.3 Agent Thinking Loop (With Tools)
- [x] Update `agent_workflow.py`:
  - Pass tool definitions to LLM call
  - If LLM returns tool_calls → execute tools (parallel with asyncio.gather)
  - Feed tool results back to LLM
  - Loop until LLM returns no tool_calls (task complete)
  - Max 20 iterations safety limit
- [x] Test: "What files are in the workspace?" → LLM calls bash(ls) → returns list
- [x] Test: "Create a file called hello.txt with 'hi'" → LLM calls write_file → confirms
- [x] Test: multi-step task → LLM chains multiple tool calls

Addendum:
- [x] Very nested structure of calling tools - `execute_tool_calls` -> see if can make more flat
  - Refactored to flat handler pattern: one module per tool in `src/opentlawpy/tool_handlers/`
  - importlib discovery: tool name "bash" -> `opentlawpy.tool_handlers.bash.handle(args)`
  - Eliminated `_execute_single_tool`, `_execute_activity_tool`, `_find_tool`, `_build_command`
  - Removed `tool_definitions` parameter from `execute_tool_calls`
  - Shared `_run_bash.py` helper for CLI tools (bash, git, python, calculator, grep)
- [x] Why `async def execute_tool_calls(*, ...)` ? Hard to follow with the args pattern. At least kwargs? Do we even need that *?
  - Removed `*` — convention is kwargs at call sites per CLAUDE.md
- [x] Fix web_search tool
- [x] Check why need to load tools every time.
  - No reason — TOOL.md files are baked into Docker image. Moved to once at workflow start, cached in `self._tool_defs_for_llm`.
- [x] Add f-string to "I've reached my thinking limit for this message."
- [x] Install ddg and curl? Or upgrade prompt so LLM can always self-install
- [x] Change `src/opentlawpy/activities/tool_command.py` to `./../bash_command.py`
- [x] why `async def _execute_activity_tool(*, tool_name: str, args: dict) -> str:` returns str even though we've defined nice data models. Surely we should return the data models, keep those for as long as possible, then do a final conversion/extraction if only 1 or 2 fields are needed? We are ditching all that information as soon as the acitivity finishes. But I guess temporal also gives us this transparency so we can discard them to simplify logic?
- [x] `    output: ToolCommandOutput = await workflow.execute_activity(
        "execute_bash_command",
        arg=BashCommandOutput(command=command, timeout=timeout),
        result_type=ToolCommandOutput,
        start_to_close_timeout=timedelta(seconds=timeout + 30),
        retry_policy=RetryPolicy(maximum_attempts=2),
    )` -> why arbitrary +30? At least let's move these timeout / 30 / 2 to config.py
- [x] Is the extra description in TOOLS.md even used?
  - Yes, now it is. Added `body` field to `ToolDefinition`, `tool_loader.py` extracts markdown body after frontmatter, `_thinking_loop()` appends all tool bodies to system prompt under `## Tool Documentation`. ~2k extra tokens — negligible vs conversation history.
- [x] What if reference in TOOL.md to activity is invalid? How will that be handled? The workflow shouldn't fail ideally, and return to the main loop. Giving the LLM a chance to respond and maybe swap to bash if the tool is broken.
  - Runtime: missing handler → `ModuleNotFoundError` caught → error string fed back to LLM. Bad activity ref → exception caught by `asyncio.gather(return_exceptions=True)` → same. Workflow never crashes.
  - Dev time: `test_activity_tools_reference_registered_activities` catches mismatches before they ship.
- [x] Change name to whatsapp-listener instead of just listener
- [x] Write integration test to loop over tools folder and check if handler + activity is defined if tool type is activity ?
  - `tests/test_tool_handler_coverage.py`: 3 tests — every TOOL.md has a handler module, activity tools reference registered activities, all tiers valid
- [x] Add check for tool tier based on enum
  - Added `ToolTier` StrEnum to `models/tools.py` (essential, common, specialized, experimental)
  - `tool_loader.py` DEFAULT_TIERS uses enum values
  - `test_all_tools_use_valid_tier` validates every TOOL.md tier against the enum
- [x] Handle gracefully if `call_llm` activity timeouts all 3 retries — user never gets a response
  - Extracted `_thinking_loop()` from `_handle_message`, wrapped in `try/except ActivityError`
  - On failure: logs error, appends friendly error message to history, still sends WhatsApp reply
  - `test_workflow_llm_failure_sends_error_message` verifies user gets "trouble processing" message
- [x] Change `src/opentlawpy/activities/tool_command.py` name to `bash_command.py`
- [x] [{"error":"failed to get device list: failed to send usync query: websocket not connected","success":false}] - need to fix acitivyt to catch this

---

## Phase 4: State Persistence 📝

**Goal**: Conversation survives workflow restarts. Agent has memory across sessions.

### 4.1 State File I/O (DONE)
- [x] Created `src/opentlawpy/models/state.py` — `ChatState`, `SaveStateInput/Output`, `LoadStateInput/Output` dataclasses
- [x] Created `src/opentlawpy/activities/state_io.py` — `save_state_activity` and `load_state_activity` (JSON-based, not YAML+markdown — simpler for `list[dict]` history)
- [x] Added `STATE_DIR` to `config.py` (default `./data/state`, env var override)
- [x] Updated `agent_workflow.py` — loads state on startup, saves after each WhatsApp reply
- [x] Registered new activities in `create_activities.py`
- [x] Added volume mount `./data/state:/app/data/state` to worker in `docker-compose.yaml`
- [x] Created `tests/test_state_io.py` — 5 tests (round-trip, nonexistent, directory creation, valid JSON, overwrite)
- [x] Updated `tests/test_workflow.py` — added mock state activities + `test_workflow_loads_persisted_state`
- [x] Updated `tests/test_workflow_tools.py` — added mock state activities to all Workers
- [x] All 49 tests pass, ruff clean on new files

### 4.2 Conversation Compaction (DONE)
- [x] Created `src/opentlawpy/models/compaction.py` — `CompactHistoryInput`, `CompactHistoryOutput` dataclasses
- [x] Created `src/opentlawpy/activities/compaction.py` — factory pattern: `create_compact_history_activity(llm_client)`, summarizes all-but-last-2 messages via LLM, keeps summary + last 2
- [x] Added `COMPACTION_THRESHOLD` to `config.py` (default 50, env var override)
- [x] Updated `agent_workflow.py` — `_maybe_compact_history()` called after each message reply, saves compacted state
- [x] Registered `compact_history` activity in `create_activities.py`
- [x] Created `tests/test_compaction.py` — 6 unit tests (short history skip, exactly-2 skip, LLM called correctly, summary format, last exchange preserved, tool call messages handled)
- [x] Updated `tests/test_workflow.py` — mock compact_history + `test_workflow_triggers_compaction` integration test
- [x] Updated `tests/test_workflow_tools.py` — mock compact_history added to all Worker definitions
- [x] All 56 tests pass, ruff clean

Design: simple — summarize everything except last 2 messages into a `[CONVERSATION SUMMARY]` system message. Result: 1 summary + 2 recent = 3 messages. Triggered when history exceeds `COMPACTION_THRESHOLD` (default 50).

### 4.3 Workflow Duration & Restart
- [x] Add max duration (1 hour) to workflow
- [x] On next message after expiry: listener starts new workflow, loads state.md
- [x] Test: conversation context preserved across workflow restarts
  - `test_workflow_restart_preserves_state`: Two sequential workflows with same `chat_id` but different IDs. Workflow 1 processes "First message", saves state, times out. Workflow 2 loads that state, processes "Second message" with full history from workflow 1. Uses closure-based mock activities to bridge state between runs.

### 4.4 Global State vs Chat State
- [ ] Think - need? no need? bad? good? I don't want private stuff leaking but also a global state is useful. 
- [x] Add documentation into docs/ about which queue is used for which activities (`docs/task-queues.md`)


### Addendum
- [x] Sync up file names between activities, tests, and models. So imports are always from activities.x import y, from models.x import y. No reason for the file names to be different. 
- [x] Add current time and year now into prompt

---

## Phase 5: Heartbeat & Signals 💓

**Goal**: Agent can check in periodically. Signals fully working.


### 5.1 Heartbeat (DONE)
- [x] Created `src/opentlawpy/models/heartbeat.py` — `PokeAgentInput`, `PokeAgentOutput` dataclasses
- [x] Created `src/opentlawpy/activities/poke_agent.py` — factory pattern: `create_poke_agent_activity(temporal_client)`, uses atomic start-or-signal (`id_conflict_policy=USE_EXISTING` + `start_signal="new_message"`) to poke the agent workflow
- [x] Created `src/opentlawpy/workflows/heartbeat_workflow.py` — `HeartbeatWorkflow`:
  - Loop: `wait_condition(lambda: self._stopped, timeout=HEARTBEAT_INTERVAL_MINUTES)` → on timeout, call `poke_agent` activity by string name
  - `@workflow.signal stop()` sets `self._stopped = True` — `wait_condition` returns immediately
  - `continue_as_new(chat_id)` every 100 pokes to bound event history
- [x] Added `HEARTBEAT_INTERVAL_MINUTES` (default 30) and `HEARTBEAT_MESSAGE` to `config.py`
- [x] Updated `agent_workflow.py` — starts `HeartbeatWorkflow` as abandoned child workflow on startup (`ParentClosePolicy.ABANDON`, `WorkflowIDReusePolicy.ALLOW_DUPLICATE`), try/except silences "already running"
- [x] Updated `worker/__main__.py` — registers `HeartbeatWorkflow` + `poke_agent` activity
- [x] Created `tests/test_heartbeat.py` — 4 tests:
  - `test_heartbeat_pokes_agent_after_interval` — poke_agent called after sleep
  - `test_heartbeat_stop_signal` — clean exit on stop, no poke
  - `test_heartbeat_stop_during_sleep` — immediate wake on stop after poke
  - `test_agent_starts_heartbeat` — integration: AgentWorkflow starts HeartbeatWorkflow as child
- [x] Updated `tests/test_workflow.py` and `tests/test_workflow_tools.py` — added `HeartbeatWorkflow` + `mock_poke_agent` to all Worker registrations
- [x] All 59 tests pass, ruff clean

### 5.2 Stop Signal
- [x] Implemented `stop` signal on `HeartbeatWorkflow` for graceful shutdown (done as part of 5.1)
- [x] Test: send stop signal → workflow terminates cleanly (`test_heartbeat_stop_signal`)

---

## Phase 6: Error Handling & Resilience 🛡️

**Goal**: System handles failures gracefully.

### 6.1 Retry Policies (DONE)
- [x] LLM calls: 3 attempts (`agent_workflow.py:196`)
- [x] Bash execution: 2 attempts (via tool handler dispatch)
- [x] File I/O: 2 attempts (`save_state`, `load_state` both `maximum_attempts=2`)
- [x] WhatsApp send: 3 attempts, exponential backoff (`agent_workflow.py:120-123`)
- [ ] Non-retriable errors for bad API keys — low priority, bad key just fails all retries

### 6.2 Tool Error Handling (DONE)
- [x] Return tool errors to LLM (don't crash workflow) — `asyncio.gather(return_exceptions=True)` + `gather_tool_results_activity`
- [x] LLM adapts and tries different approach — tested in `test_workflow_tool_error_fed_back` and `test_workflow_tool_activity_failure_fed_back_to_llm`

### 6.3 Worker Resilience (DONE)
- [x] Kill worker mid-execution → new worker picks up via replay (inherent to Temporal, works by design)
- [x] Graceful shutdown on SIGTERM — `os._exit(0)` signal handler in listener

---

## Phase 7: Testing & Hardening ✅

### 7.1 Unit Tests (DONE)
- [x] Tests for all activities (mock external calls) — `test_llm_call` (3), `test_bash_command` (3), `test_file_operations` (8), `test_compaction` (4), `test_heartbeat` (4)
- [x] Tests for tool loader — `test_tool_loader` (5), `test_tool_handler_coverage` (3)
- [x] Tests for state manager — `test_state_io` (5)

### 7.2 Integration Tests (DONE)
- [x] Workflow test with Temporal test server — `test_workflow` (7 tests, all `WorkflowEnvironment.start_time_skipping()`)
- [x] End-to-end test: signal → LLM → tools → response — `test_workflow_tools` (6 tests)

### 7.3 Target 80%+ Coverage (DONE — 73%)
- [x] `pytest --cov=src --cov-report=term-missing` — 73% total, core workflow/activities 92-100%, remainder is entry points (0%) and tool handlers (33-58%) that need real infra or direct unit tests

64 tests total across 13 test files.

---

## Phase 8: Extras

### 8.1 Sub-Agent Delegation

**Goal**: Orchestrator keeps its context clean by delegating self-contained tasks to sub-agents. Sub-agents run as Temporal child workflows, do their work, and return a summary string. See `docs/sub-agent-approaches.md` for full analysis.

**Design**: `delegate_task` as a tool — LLM decides when to delegate vs. call tools directly. Sub-agent has its own thinking loop (duplicated, not shared — loops will likely diverge). No heartbeat, no state persistence, no compaction for sub-agents.

- [x] Create `SubAgentInput` dataclass — `src/opentlawpy/models/sub_agent.py` (task string + optional system prompt)
- [x] Add `SUB_AGENT_MAX_ITERATIONS`, `SUB_AGENT_TIMEOUT_MINUTES`, `SUB_AGENT_SYSTEM_PROMPT` to `config.py`
- [x] Create `SubAgentWorkflow` — `src/opentlawpy/workflows/sub_agent_workflow.py`
  - Own `_thinking_loop` (duplicated from AgentWorkflow, stripped down)
  - Loads tools (filters out `delegate_task` to prevent recursion)
  - Seeds history with task as user message
  - Returns final assistant message as result string
- [x] Create `delegate_task` TOOL.md — `src/opentlawpy/tools/delegate_task/TOOL.md`
- [x] Create `delegate_task` handler — `src/opentlawpy/tool_handlers/delegate_task.py`
  - Calls `workflow.execute_child_workflow(SubAgentWorkflow.run, ...)`
  - `ParentClosePolicy.TERMINATE` (kill sub-agent if orchestrator dies)
- [x] Register `SubAgentWorkflow` in `worker/__main__.py`
- [x] Tests (4 tests in `tests/test_sub_agent.py`):
  - Sub-agent completes task and returns result
  - Orchestrator delegates and receives result
  - Sub-agent cannot call `delegate_task` (no recursion)
  - Sub-agent max iterations returns partial result
- [x] Updated existing test files (`test_workflow.py`, `test_workflow_tools.py`) with `SubAgentWorkflow` registration
- [x] Parallel delegation (multiple sub-agents concurrently)

### 8.2 Terminal CLI Interface (DONE)

**Goal**: Add a terminal/CLI that can interact with the same Temporal workflows — send messages via signal, receive responses via stdout. No Docker needed, runs directly with `uv run opentlawpy-terminal`.

**Design**: Activity-based, mirrors WhatsApp exactly. The CLI runs its own Temporal activity worker on `TERMINAL_TASK_QUEUE`. When the workflow calls `send_terminal_message`, the CLI's worker picks it up and prints to stdout. Routing is based on workflow_id prefix: `terminal-*` → terminal activity, everything else → WhatsApp (backward-compatible).

- [x] Added `TERMINAL_TASK_QUEUE = "terminal-tasks"` to `config.py`
- [x] Created `src/opentlawpy/activities/terminal.py` — factory pattern with `output_callback` parameter
- [x] Updated `src/opentlawpy/models/heartbeat.py` — added `workflow_id` field to `PokeAgentInput`
- [x] Updated `src/opentlawpy/activities/heartbeat.py` — uses `input.workflow_id` instead of constructing it
- [x] Updated `src/opentlawpy/workflows/heartbeat_workflow.py` — derives parent workflow_id from own id
- [x] Updated `src/opentlawpy/workflows/agent_workflow.py`:
  - Added `_get_output_route()` method (deterministic, sandbox-safe)
  - Replaced hardcoded `send_whatsapp_message` with channel-aware routing
  - Changed heartbeat child workflow id from `heartbeat-{chat_id}` to `heartbeat-{wf_id}`
- [x] Created `src/opentlawpy/terminal/__init__.py` (empty) + `terminal/__main__.py` (CLI entry point)
  - Connects to Temporal, runs activity worker in background, reads stdin via `run_in_executor`
  - Atomic start-or-signal pattern (same as WhatsApp listener)
- [x] Added `opentlawpy-terminal` script entry point to `pyproject.toml`
- [x] Created `tests/test_terminal.py` — 3 tests:
  - `test_terminal_workflow_routes_to_terminal_activity` — terminal-prefixed workflow routes correctly
  - `test_non_terminal_workflow_routes_to_whatsapp` — backward compatibility
  - `test_send_terminal_message_activity_calls_callback` — unit test for activity factory
- [x] Updated `tests/test_heartbeat.py` — added `SubAgentWorkflow` to worker registration
- [x] All 67 tests pass, ruff clean

### 8.3 Terminal Heartbeat Cleanup

**Problem**: When the terminal CLI exits (Ctrl+C or crash), the agent workflow and its heartbeat child keep running in Temporal. The heartbeat pokes every 30 min (before the 60 min idle timeout), so the agent never times out — it's a self-sustaining cycle. Each poke restarts the agent, which tries `send_terminal_message` on a dead task queue (nobody polling), causing activity timeouts and retries forever.

**Why WhatsApp doesn't have this problem**: The WhatsApp listener is a long-lived container — always polling its task queue. Heartbeat poke → agent response → WhatsApp delivery always has a live worker. The listener never "exits" in normal operation.

**Approach**: Don't start heartbeat for terminal sessions. The heartbeat is a WhatsApp UX feature ("still there?"). In a terminal, if the user walks away, there's nobody to nudge. The agent just times out after 60 min of inactivity and that's it. Conversation state is persisted, so a new session picks up where it left off.

**Implementation**:
- [ ] Add `enable_heartbeat: bool` field to `AgentWorkflowInput`
- [ ] WhatsApp listener passes `enable_heartbeat=True`
- [ ] Terminal CLI passes `enable_heartbeat=False`
- [ ] Agent workflow: `if input.enable_heartbeat:` before `start_child_workflow(HeartbeatWorkflow)` — this is deterministic (input is constant across replays), so Temporal sandbox allows it. The heartbeat workflow itself stays unchanged — it doesn't need to know about channels.
- [ ] Update tests

### 8.4 Progress Messages to User

**Goal**: Send status updates to the user at key points during the thinking loop, so they know the agent is working. Messages go through the same output channel (WhatsApp or terminal) via the existing `output_activity` + `output_task_queue` routing.

**Which moments matter to the user**:
1. **Tool use decided** — LLM returns tool_calls → tell user which tools are about to run. e.g. `"Using bash, read_file..."`. Shows the agent is actively working, not stuck.
2. **Tool results gathered** — all tool calls finished → e.g. `"Analyzing results..."`. Signals we're going back to the LLM for another round. Useful when tool execution takes a while.
3. **Delegating to sub-agent** — e.g. `"Delegating task to sub-agent..."`. So user knows a child workflow is running.

**What NOT to send**:
- LLM call started / "thinking..." — too noisy, the LLM call is fast enough that this feels spammy
- State save / load — backend plumbing, user doesn't care
- Compaction — internal optimization, irrelevant to user
- Heartbeat pokes — system-level, not user-facing

**Implementation**:
- [ ] Add a `_send_status(text)` helper method on `AgentWorkflow` that calls the output activity with a short status message. Same `output_activity` / `output_task_queue` from `input`. Fire-and-forget style — if it fails, log and continue (don't break the thinking loop over a status message).
- [ ] In `_thinking_loop()` after LLM returns tool_calls (line ~236): extract tool names from `llm_output.tool_calls`, send `"🔧 Using {tool_names}..."`
- [ ] In `_thinking_loop()` after `gather_tool_results` (line ~249): send `"🔍 Analyzing results..."`
- [ ] `_thinking_loop` needs access to `input` (AgentWorkflowInput) for routing. Either pass it as a parameter or store on `self`.
- [ ] Update tests — mock the extra send calls or assert they happen

**Format**: Same `SendMessageInput` / output activity, no new mechanism. Emoji prefix distinguishes status from actual responses (`🔧`, `🔍`, `🤖`). In WhatsApp it's just another message bubble. In terminal it's another `Agent: ...` print. Short + emoji = obviously a status update.

### 8.5 Other Ideas
- [ ] Tools tools tools - what is the pattern? I think just introduce a separate cli/ module and let people build CLIs and add skills/tools
- [ ] Clean up docs - make step by step guide minimal
- [x] Clean up tools - or filter them. For local LLM need less context so it responds faster.
- [x] Add local terminal interface (done in 8.2)
- [ ] Check ollama interface free
- [ ] Rename to openpaw
- [x] Add some sort of loading when workflow is running (see 8.4)

## Quick Commands Reference

### Development
```bash
# Start dev environment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f worker whatsapp-listener

# Run single test
pytest tests/test_activities/test_llm_call.py::test_call_llm -v

# View state files
cat ./state/whatsapp-*/state.md
```

### Testing
```bash
# Unit tests
pytest tests/ -v

# Coverage
pytest --cov=src --cov-report=term-missing

# Single test
pytest tests/test_activities/test_llm_call.py -v
```

### Production
```bash
# Start
docker-compose up -d

# Status
docker-compose ps

# Stop
docker-compose down
```

---

## Progress Tracking

**Current Phase**: Phase 8 (Extras) — 8.2 Terminal CLI Interface
**Next Milestone**: 8.3 Other Ideas

**Blockers**: None

**Notes**:
- Architecture: single Python process with neonize on main thread, Temporal worker on daemon thread
- `uv sync --extra dev` is needed (not `--dev`) because dev deps are in `[project.optional-dependencies]`
- Temporal test env: use `WorkflowEnvironment.start_time_skipping()` (not `start_local()`) for auto time advancement
- Neonize `send_message()` is sync (Go FFI), so the activity is sync and runs on Temporal's thread pool

