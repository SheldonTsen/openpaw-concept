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
- [ ] Fix web_search tool
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
- [ ] Is the extra description in TOOLS.md even used?
- [x] What if reference in TOOL.md to activity is invalid? How will that be handled? The workflow shouldn't fail ideally, and return to the main loop. Giving the LLM a chance to respond and maybe swap to bash if the tool is broken.
  - Runtime: missing handler → `ModuleNotFoundError` caught → error string fed back to LLM. Bad activity ref → exception caught by `asyncio.gather(return_exceptions=True)` → same. Workflow never crashes.
  - Dev time: `test_activity_tools_reference_registered_activities` catches mismatches before they ship.
- [ ] Change name to whatsapp-listener instead of just listener
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

---

## Phase 4: State Persistence 📝

**Goal**: Conversation survives workflow restarts. Agent has memory across sessions.

### 4.1 State File I/O
- [ ] Create `src/activities/state_file_io.py` — read/write state.md
- [ ] Create `src/utils/state_manager.py` — parse/serialize state.md (YAML frontmatter + markdown)
- [ ] Workflow loads state.md on startup, saves after each message

### 4.2 Conversation Compaction
- [ ] Create `src/activities/conversation_compaction.py`
- [ ] Trigger when conversation > 100 messages
- [ ] Keep first 5 + summary + last 20 messages

### 4.3 Workflow Duration & Restart
- [ ] Add max duration (1 hour) to workflow
- [ ] On next message after expiry: listener starts new workflow, loads state.md
- [ ] Test: conversation context preserved across workflow restarts

---

## Phase 5: Heartbeat & Signals 💓

**Goal**: Agent can check in periodically. Signals fully working.

### 5.1 Heartbeat
- [ ] Implement heartbeat timer (30 min default)
- [ ] On timeout: inject system prompt "Check in and report status"
- [ ] Configurable via `update_heartbeat` signal

### 5.2 Stop Signal
- [ ] Implement `stop` signal for graceful shutdown
- [ ] Test: send stop signal → workflow terminates cleanly

---

## Phase 6: Error Handling & Resilience 🛡️

**Goal**: System handles failures gracefully.

### 6.1 Retry Policies
- [ ] LLM calls: 3 attempts, exponential backoff
- [ ] Bash execution: 2 attempts
- [ ] File I/O: 2 attempts
- [ ] WhatsApp send: 3 attempts
- [ ] Non-retriable errors for bad API keys

### 6.2 Tool Error Handling
- [ ] Return tool errors to LLM (don't crash workflow)
- [ ] LLM adapts and tries different approach

### 6.3 Worker Resilience
- [ ] Test: kill worker mid-execution → new worker picks up via replay
- [ ] Graceful shutdown on SIGTERM

---

## Phase 7: Testing & Hardening ✅

### 7.1 Unit Tests
- [ ] Tests for all activities (mock external calls)
- [ ] Tests for tool loader
- [ ] Tests for state manager

### 7.2 Integration Tests
- [ ] Workflow test with Temporal test server
- [ ] End-to-end test: signal → LLM → tools → response

### 7.3 Target 80%+ Coverage
- [ ] `pytest --cov=src --cov-report=term-missing`

---

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

**Current Phase**: Phase 3 (Tool Execution) — 3.1, 3.2 done
**Next Milestone**: Phase 3.3 Agent Thinking Loop (With Tools)

**Blockers**: None

**Notes**:
- Architecture: single Python process with neonize on main thread, Temporal worker on daemon thread
- `uv sync --extra dev` is needed (not `--dev`) because dev deps are in `[project.optional-dependencies]`
- Temporal test env: use `WorkflowEnvironment.start_time_skipping()` (not `start_local()`) for auto time advancement
- Neonize `send_message()` is sync (Go FFI), so the activity is sync and runs on Temporal's thread pool
