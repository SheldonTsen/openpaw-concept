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

Follow Up:
- [ ] directories should be src/opentlawpy 
- [ ] imports should be from opentlawpy import x (pyproject.toml might need updating for this to work
- [ ] Remove dockerfile.dev and modify docker-compose.dev.yml to use docker compose watch. While the main docker-compose does not use docker compose watch. 
- [ ] my_phone_number=MY_PHONE_NUMBER, change to my_whatsapp_number=MY_WHATSAPP_NUMBER (keep same as .env declaration). No reason to be different
- [ ] move TASK_QUEUE = "agent-tasks" NAMESPACE = "opentlawpy" to a config.py to hold all code related config in one place. 
- [ ] move logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
) to a custom_logging.py and re-use that (repeated again in src/whatsapp/__main__.py)
- [ ] move TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
MY_PHONE_NUMBER = os.environ.get("MY_PHONE_NUMBER", os.environ.get("MY_WHATSAPP_NUMBER", ""))
NEONIZE_DB_PATH = os.environ.get("NEONIZE_DB_PATH", "./neonize.db")
 to the central config.py (in src/whatsapp/__main__.py at the moment)
- [ ] Remove duplication in TASK_QUEUE = "agent-tasks"
NAMESPACE = "opentlawpy" from src/worker/worker.py
- [ ] Explain tests 
async def test_workflow_echoes_message():
    """Workflow receives a signal and calls send_whatsapp_message with echo response."""
    activity_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_send_whatsapp_message],
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="1234567890",
                id="test-workflow-1",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["1234567890", "Hi there"],
            )

            # Time-skipping env auto-advances to the 60-min timeout
            await handle.result()

    assert len(activity_calls) == 1
    assert activity_calls[0].phone_number == "1234567890"
    assert activity_calls[0].text == "Hello! I received: Hi there"


async def test_workflow_start_signal_pattern():
    """Verify the atomic start-or-signal pattern works correctly."""
    activity_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_send_whatsapp_message],
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="9876543210",
                id="test-workflow-2",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["9876543210", "Hello world"],
            )

            await handle.result()

    assert len(activity_calls) >= 1
    assert activity_calls[0].phone_number == "9876543210"
    assert activity_calls[0].text == "Hello! I received: Hello world"

this seems repeated twice. I don't see what the difference is between these 2 tests?
- [ ] Validate if we need all these if else     def _get_message_timestamp(self, message: MessageEv) -> float:
        """Extract message timestamp as Unix seconds."""
        ts = message.Info.Timestamp
        if isinstance(ts, (int, float)):
            return float(ts)
        if hasattr(ts, "seconds"):
            return float(ts.seconds)
        if hasattr(ts, "timestamp"):
            return ts.timestamp()
        return time.time()
- [ ] add logging for these 2         msg_time = self._get_message_timestamp(message=message)
        if msg_time < self._start_time:
            return

        text = message.Message.conversation or message.Message.extendedTextMessage.text
        if not text:
            return


Next Follow Up:
- [ ] Clarify on neonize.db in listener pattern - seems a bit odd. If we refer to the same DB is that the same client?



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
- [ ] Verify: edit workflow code → worker auto-restarts → no rebuild needed
- [ ] Verify: `docker-compose logs -f agent --tail=20` shows reload
- [ ] Change "Hello!" to "Hey!" in workflow, confirm change takes effect without rebuild

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

### 2.1 LLM Call Activity
- [ ] Create `src/activities/llm_call.py` — call Anthropic API
- [ ] Create `src/llm/__init__.py`
- [ ] Create `src/llm/anthropic_client.py` — wrapper around Anthropic SDK
- [ ] Test: activity calls Claude, returns response text
- [ ] Add retry policy (3 attempts, exponential backoff)

### 2.2 Agent Thinking Loop (No Tools Yet)
- [ ] Update `agent_workflow.py`:
  - On message: call LLM activity with conversation history
  - Return LLM's text response via WhatsApp
  - Store conversation history in workflow state (in-memory, not persisted yet)
- [ ] Test: send WhatsApp message → get actual LLM response back
- [ ] Test: send follow-up message → LLM has context from previous message

### 2.3 System Prompt
- [ ] Add configurable system prompt to WorkflowConfig
- [ ] Load system prompt from file or env var
- [ ] Test: agent responds according to system prompt personality

---

## Phase 3: Tool Execution 🔧

**Goal**: LLM can call tools (bash, read_file, write_file). Multi-step reasoning works.

### 3.1 Tool Definitions
- [ ] Create `tools/bash/TOOL.md`
- [ ] Create `tools/read_file/TOOL.md`
- [ ] Create `tools/write_file/TOOL.md`
- [ ] Create `src/utils/tool_loader.py` — load TOOL.md files, convert to Anthropic format

### 3.2 Tool Activities
- [ ] Create `src/activities/bash_executor.py` — execute bash with safety checks
- [ ] Create `src/activities/file_operations.py` — read_file, write_file

### 3.3 Agent Thinking Loop (With Tools)
- [ ] Update `agent_workflow.py`:
  - Pass tool definitions to LLM call
  - If LLM returns tool_calls → execute tools (parallel with asyncio.gather)
  - Feed tool results back to LLM
  - Loop until LLM returns no tool_calls (task complete)
  - Max 20 iterations safety limit
- [ ] Test: "What files are in the workspace?" → LLM calls bash(ls) → returns list
- [ ] Test: "Create a file called hello.txt with 'hi'" → LLM calls write_file → confirms
- [ ] Test: multi-step task → LLM chains multiple tool calls

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

**Current Phase**: Phase 1 (Lean E2E "Hello World") — code complete, pending manual E2E verification
**Next Milestone**: Phase 1.4 E2E test (docker-compose up, send WhatsApp message, verify echo)

**Blockers**: None

**Notes**:
- Architecture: single Python process with neonize on main thread, Temporal worker on daemon thread
- `uv sync --extra dev` is needed (not `--dev`) because dev deps are in `[project.optional-dependencies]`
- Temporal test env: use `WorkflowEnvironment.start_time_skipping()` (not `start_local()`) for auto time advancement
- Neonize `send_message()` is sync (Go FFI), so the activity is sync and runs on Temporal's thread pool
