# openpaw Architecture Plan

## Executive Summary

This document describes the architecture for a Temporal-based agentic system inspired by OpenClaw. The system will provide full visibility into agent operations through Temporal's UI while maintaining persistent state across workflow runs. The architecture leverages Temporal's workflow orchestration, activity execution, signals, and cron scheduling to build a robust, observable, and fault-tolerant agent system.

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Core Concepts & Mapping](#core-concepts--mapping)
3. [Critical Temporal Concepts](#critical-temporal-concepts) ⚠️ **READ THIS FIRST**
4. [System Components](#system-components)
5. [WhatsApp Integration (MVP)](#whatsapp-integration-mvp) 📱 **ENTRY POINT**
6. [Error Handling & Retries (MVP)](#error-handling--retries-mvp) 🛡️ **RESILIENCE**
7. [File Layout](#file-layout)
8. [Data Schemas](#data-schemas)
9. [Pseudo Code Interfaces](#pseudo-code-interfaces)
10. [Implementation Plan](#implementation-plan)
11. [Testing Strategy](#testing-strategy)
12. [Deployment & Docker Compose](#deployment--docker-compose)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         External Triggers                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  Slack   │  │  Email   │  │   HTTP   │  │  Cron    │  │  Manual  │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
└───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────┘
        │             │             │             │             │
        └─────────────┴─────────────┴─────────────┴─────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │   Gateway Service (Optional)   │
                    │  - Signal Adaptor              │
                    │  - Webhook Receiver            │
                    │  - Message Router              │
                    └───────────────┬────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │    Temporal Server Cluster     │
                    │  - Workflow Orchestration      │
                    │  - Durable State               │
                    │  - Signal Delivery             │
                    │  - Cron Scheduling             │
                    └───────────────┬────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐         ┌────────▼────────┐        ┌────────▼────────┐
│ Agent Workflow │         │ Agent Workflow  │        │ Agent Workflow  │
│   (Instance 1) │         │   (Instance 2)  │        │   (Instance N)  │
│                │         │                 │        │                 │
│ - LLM Loop     │         │  - LLM Loop     │        │  - LLM Loop     │
│ - State mgmt   │         │  - State mgmt   │        │  - State mgmt   │
│ - Tool calls   │         │  - Tool calls   │        │  - Tool calls   │
└───────┬────────┘         └────────┬────────┘        └────────┬────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                        ┌───────────▼────────────┐
                        │   Activity Workers     │
                        │                        │
                        │  ┌──────────────────┐  │
                        │  │ Bash Executor    │  │
                        │  └──────────────────┘  │
                        │  ┌──────────────────┐  │
                        │  │ LLM Caller       │  │
                        │  └──────────────────┘  │
                        │  ┌──────────────────┐  │
                        │  │ State File I/O   │  │
                        │  └──────────────────┘  │
                        │  ┌──────────────────┐  │
                        │  │ Webhook Sender   │  │
                        │  └──────────────────┘  │
                        └────────────────────────┘
                                    │
                        ┌───────────▼────────────┐
                        │   Persistent Storage   │
                        │                        │
                        │  - state.md (per flow) │
                        │  - Workspace files     │
                        └────────────────────────┘
```

### Data Flow

1. **Incoming Signal**: External trigger → Gateway → Temporal Signal → Agent Workflow
2. **Agent Execution**: Workflow → Activity (LLM call) → Get response → Activity (Bash) → Execute tool
3. **State Persistence**: After each step → Write to state.md → Workflow state update
4. **Heartbeat**: Every X minutes → Workflow self-signals or continues based on timer
5. **Workflow Termination**: After X duration → Gracefully close → Cron restarts

### Agent Thinking Loop (The "Brain")

The core of each Agent Workflow is the thinking loop that enables multi-step reasoning like OpenClaw:

```python
# User sends message
workflow receives signal → new_message("user", "Find all TODO comments")

# Agent thinking loop (inside _process_messages)
for iteration in range(max_iterations=20):
    # 1. Call LLM with conversation history
    llm_response = await call_llm_activity(conversation)

    # 2. LLM returns structured response with optional tool calls
    # Example response:
    # {
    #   "response_text": "I'll search for Python files first",
    #   "tool_calls": [{"name": "bash", "arguments": {"command": "find . -name '*.py'"}}]
    # }

    # 3. Check if LLM is done (no tools = task complete)
    if not llm_response.tool_calls:
        break  # LLM finished, return answer to user

    # 4. LLM wants tools → execute them in parallel
    tool_results = await execute_tools(llm_response.tool_calls)
    # Results: ["app.py\nutils.py\ntest.py"]

    # 5. Add results to conversation
    conversation.append(tool_results)

    # 6. Loop back → LLM sees results and decides next action
    # Next iteration might:
    #   - Call more tools: grep each file for TODOs
    #   - Ask user for clarification
    #   - Return final answer
```

**Key Insights:**
- **LLM decides when it's done** by returning `tool_calls: []` (empty)
- **Each iteration is visible** in Temporal UI as separate activities
- **Multi-step reasoning** happens naturally: find files → search files → write summary → done
- **Safety limit** of 20 iterations prevents infinite loops
- **Conversation history** grows with each iteration (user msg → LLM → tools → LLM → tools...)

**Example Multi-Step Task:**
```
User: "Find all TODO comments and create a summary"

Iteration 1:
  LLM: "I'll search for Python files"
  Tool: bash("find . -name '*.py'") → ["app.py", "utils.py"]

Iteration 2:
  LLM: "Now I'll check each file for TODOs"
  Tools: [bash("grep TODO app.py"), bash("grep TODO utils.py")]
  Results: ["app.py:10: TODO: Add tests", "utils.py:45: TODO: Optimize"]

Iteration 3:
  LLM: "I'll create the summary file"
  Tool: write_file("summary.md", "# TODOs\n- app.py:10: Add tests\n...")
  Result: "Success"

Iteration 4:
  LLM: "Task complete! Created summary.md with 2 TODOs found."
  Tool calls: [] (none)
  → Loop breaks, workflow waits for next message
```

---

## Core Concepts & Mapping

### OpenClaw → Temporal Mapping

| **OpenClaw Component** | **Temporal Implementation** | **Rationale** |
|------------------------|----------------------------|---------------|
| **Agent Run (Session)** | **Long-Running Workflow** | Workflow maintains conversation state, orchestrates LLM reasoning loop |
| **Tool Execution (bash)** | **Activity** | Activities are stateless, retryable, can report heartbeats |
| **Session State** | **Workflow State + state.md** | Workflow variables + persistent markdown file for cross-run memory |
| **Message Routing** | **Workflow Start Logic** | Route to appropriate workflow based on channel/user |
| **Cron Jobs** | **Scheduled Workflows** | Use Temporal's native cron scheduling |
| **Hooks/Lifecycle Events** | **Signals** | Temporal signals for external triggers mid-execution |
| **Auth Profile Rotation** | **Activity Retry Policy** | Automatic retry with different credentials |
| **Model Fallback** | **Activity with Retry** | Try different models on failure |
| **State File Read/Write** | **Activity** | Simple file I/O for state.md |
| **Webhook Delivery** | **Activity** | Send to Slack/email channels |
| **Process Management** | **Activity with Heartbeat** | Long-running bash processes report status |

### Key Design Decisions

1. **Workflow Duration Limits**:
   - Each agent workflow runs for a fixed duration (e.g., 1 hour)
   - External cron job restarts workflow after completion
   - This keeps Temporal UI clean and prevents infinite workflow history

2. **State Persistence**:
   - **In-workflow state**: Conversation history, current step
   - **state.md file**: Cross-run persistent memory (survives workflow restarts)
   - **Temporal workflow state**: Automatically persisted by Temporal

3. **Concurrency Model**:
   - Each agent workflow = one sequential LLM loop (no race conditions)
   - Multiple agents = multiple concurrent workflows (isolated state)
   - Temporal handles worker pool management

4. **Signal Handling**:
   - Workflows listen for signals: `new_message`, `stop`, `heartbeat_config_update`
   - Gateway service translates external events to Temporal signals

---

## Critical Temporal Concepts

**⚠️ READ THIS SECTION CAREFULLY** - These concepts are essential to understanding how the system works and avoiding common pitfalls.

### 1. Workflow Replay and Event History

**Key Insight:** Workflows replay from the top on every wake-up, but use event history to fast-forward.

#### How It Works

When a workflow is woken up (by signal or timeout), Temporal:
1. Loads the workflow's event history from database
2. Executes `async def run()` **from line 1**
3. Uses event history to return cached results (doesn't re-execute activities)
4. Fast-forwards to where it left off
5. Continues with new code

#### Example

```python
@workflow.run
async def run(self, config):
    # ALWAYS executes on every wake-up
    workflow_id = workflow.info().workflow_id

    # First time: Actually calls activity
    # Replay: Returns cached result from Event #3 in history (INSTANT)
    state = await workflow.execute_activity(read_state_file, ...)

    # ALWAYS executes on every wake-up
    self.state = AgentWorkflowState(...)

    while True:
        # First time: Waits for 30 minutes or signal
        # Replay after signal: Reads Event #5 (signal received), returns immediately
        has_message = await workflow.wait_condition(...)

        # NEW CODE - executes for real (not in history yet)
        if has_message:
            await self._process_messages()
```

#### Event History Example

```
Event #1: WorkflowStarted
Event #2: ActivityScheduled (read_state_file)
Event #3: ActivityCompleted (read_state_file) → result: "..."
Event #4: TimerStarted (wait_condition, 30 min)
Event #5: SignalReceived (new_message, "Check API")
Event #6: TimerCanceled
Event #7: ActivityScheduled (call_llm_activity)  ← New events start here
```

When workflow wakes up after Event #5, it replays Events #1-6 (instant), then continues with new execution.

#### Why This Matters

- ✅ **Durability**: Worker crashes → new worker replays from events → seamless continuation
- ✅ **Observability**: Full execution history in Temporal UI
- ✅ **Testing**: Replay events to reproduce bugs
- ⚠️ **Logging**: `workflow.logger.info("Started")` logs on EVERY replay
- ⚠️ **Determinism**: Code must produce same results on replay (see below)

---

### 2. Workflow vs Activity: The Critical Distinction

**Most Common Mistake:** Trying to do I/O operations in workflows instead of activities.

#### Workflows = Orchestration Only

**Workflows can:**
- ✅ Make decisions (if/else, loops)
- ✅ Call activities
- ✅ Wait for signals/timeouts
- ✅ Store state in variables
- ✅ Use `workflow.now()`, `workflow.logger`

**Workflows CANNOT:**
- ❌ Make network calls (HTTP, database, API)
- ❌ Read/write files
- ❌ Use `random.random()`, `datetime.now()`
- ❌ Do anything non-deterministic

```python
# ❌ WRONG - This will error
@workflow.defn
class MyWorkflow:
    async def run(self):
        # This fails - can't do I/O in workflow!
        response = await httpx.get("https://api.example.com")

        # This fails - non-deterministic!
        if random.random() > 0.5:
            ...

# ✅ CORRECT - Use activities for I/O
@workflow.defn
class MyWorkflow:
    async def run(self):
        # Call activity to do the I/O
        response = await workflow.execute_activity(
            call_api_activity,
            ...
        )
```

#### Activities = Actual Work

**Activities can:**
- ✅ Make network calls
- ✅ Read/write files
- ✅ Execute bash commands
- ✅ Use any libraries
- ✅ Be non-deterministic
- ✅ Send heartbeats for long operations

```python
@activity.defn
async def call_api_activity(url: str) -> dict:
    """Activities can do I/O and non-deterministic operations."""
    # This is fine - activity can do anything
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

#### Why Methods Like `_execute_tools` Are NOT Activities

```python
# This is a WORKFLOW METHOD (not an activity)
async def _execute_tools(self, tool_calls: List[ToolCall]):
    """Orchestrates tool execution - decides which activities to call."""
    tasks = [
        self._execute_single_tool(tc)  # Calls activities
        for tc in tool_calls
    ]
    return await asyncio.gather(*tasks)  # Workflow coordination

# This CALLS activities (still a workflow method)
async def _execute_single_tool(self, tool_call: ToolCall):
    """Routes to appropriate activity based on tool name."""
    if tool_call.name == "bash":
        # HERE is the activity call
        return await workflow.execute_activity(
            bash_executor_activity,  # ← This is the activity
            ...
        )
```

**Pattern:** Workflow methods orchestrate, activities execute.

---

### 3. How `workflow.wait_condition()` Actually Works

**Common Misconception:** "This will busy-loop and waste CPU!"

```python
# This does NOT spin in a loop!
while True:
    has_message = await workflow.wait_condition(
        lambda: len(self.pending_messages) > 0,
        timeout=timedelta(minutes=30)
    )
```

#### What Actually Happens

When you call `workflow.wait_condition()`:

1. **Temporal saves workflow state** to database
2. **Workflow execution stops** (not running on any worker)
3. **Worker is freed** to run other workflows
4. **Temporal sets up triggers:**
   - Timer for timeout (30 minutes)
   - Watch for signals that might change condition
5. **Zero CPU usage** while waiting

When condition becomes true OR timeout:

1. **Temporal loads workflow state** from database
2. **Schedules workflow** on an available worker
3. **Resumes execution** from replay (fast-forwards to wait_condition)
4. **Returns result** (True if condition met, False if timeout)

#### Comparison

```python
# ❌ Regular Python (busy loop - wastes CPU)
while not condition:
    await asyncio.sleep(0.1)  # Checks 10x/second

# ✅ Temporal (true blocking - zero CPU)
await workflow.wait_condition(lambda: condition, timeout=30min)
# Workflow literally doesn't exist in memory during wait
```

#### Scalability

```
1000 users, each with a workflow waiting for messages:

Regular approach:
- 1000 coroutines in memory
- Constantly checking conditions
- High CPU usage

Temporal approach:
- All 1000 workflows saved in database
- Zero workflows in memory (all paused)
- Zero CPU usage
- Each wakes up only when needed
```

---

### 4. How Signals Wake Waiting Workflows

**The Question:** "If workflow is paused at `wait_condition`, how do new messages get added to `pending_messages`?"

**The Answer:** Signals!

#### The Flow

**Step 1: Workflow Waiting**
```python
# Workflow paused here, saved in database
await workflow.wait_condition(
    lambda: len(self.pending_messages) > 0,  # Currently: []
    timeout=timedelta(minutes=30)
)
```

**Step 2: External Event (WhatsApp Message)**
```python
# User sends message
# Neonize listener receives it via WebSocket event
async def _route_message(self, message):
    workflow_id = f"whatsapp-{message.chat_id}"
    handle = temporal_client.get_workflow_handle(workflow_id)

    # Send signal to paused workflow
    await handle.signal("new_message", message.sender, message.text)
```

**Step 3: Signal Handler Executes**
```python
# Temporal wakes workflow and executes signal method
@workflow.signal
def new_message(self, sender: str, text: str):
    # This runs IMMEDIATELY when signal arrives
    msg = Message(role=MessageRole.USER, content=text)
    self.pending_messages.append(msg)  # Modifies workflow state!
    # Now: self.pending_messages = [msg]
```

**Step 4: Wait Condition Re-evaluates**
```python
# After signal handler completes, wait_condition checks again
lambda: len(self.pending_messages) > 0
# Was: len([]) > 0 → False
# Now: len([msg]) > 0 → True ✅

# Condition is true! Returns immediately
has_message = True

if has_message:
    await self._process_messages()  # Processes the message
```

#### Key Points

- ✅ Signals modify workflow state while it's "paused"
- ✅ wait_condition automatically re-evaluates after signal
- ✅ Workflow wakes up instantly (no polling delay)
- ✅ Multiple signals queue up in pending_messages
- ✅ All signals are durable (recorded in event history)

---

### 5. Workflow ID Strategy

**Critical:** Use deterministic workflow IDs for conversation continuity.

#### The Pattern

```python
workflow_id = f"{channel}-{unique_identifier}"
```

#### Examples by Use Case

**WhatsApp (one workflow per chat):**
```python
workflow_id = f"whatsapp-{message.chat_id}"
# Examples:
# "whatsapp-1234567890@c.us" (individual chat)
# "whatsapp-group-987654321@g.us" (group chat)
```

**HTTP API (one workflow per user session):**
```python
workflow_id = f"agent-{user_id}-{session_id}"
# Examples:
# "agent-alice-session42"
# "agent-bob-session99"
```

**Cron Jobs:**
```python
workflow_id = "cron-daily-summary"
# Same ID every time → same workflow instance
```

**Slack (one workflow per thread):**
```python
workflow_id = f"slack-{channel_id}-{thread_ts}"
# Example: "slack-C1234-1234567890.123456"
```

#### Why Deterministic IDs Matter

**Scenario: User sends multiple messages**

```python
# ✅ CORRECT - Deterministic ID
User: "Find TODOs"  → start workflow("whatsapp-user123")
User: "Check .js"   → signal to existing workflow("whatsapp-user123")
                    → Same workflow! Has conversation context ✅

# ❌ WRONG - Random ID
User: "Find TODOs"  → start workflow("abc-123")
User: "Check .js"   → start workflow("xyz-789")
                    → New workflow! No context ❌
```

#### How Gateway Uses IDs

```python
async def route_message(message):
    workflow_id = f"whatsapp-{message.chat_id}"

    try:
        # Try to signal existing workflow
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("new_message", message.text)
    except WorkflowNotFoundError:
        # No workflow → start new one with same ID
        await client.start_workflow(
            AgentWorkflow.run,
            id=workflow_id,  # Deterministic!
            ...
        )
```

---

### 6. End-to-End Message Flow

**Complete path: WhatsApp → Agent Response**

```
┌─────────────────────────────────────────────────────────┐
│ 1. User sends WhatsApp message                          │
│    "Check if the API is down"                           │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 2. Neonize Listener (persistent WebSocket connection)    │
│    - Receives message via Baileys/Whatsmeow event       │
│    - Parses: chat JID, sender, text                     │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 3. Listener routes to Temporal                          │
│    workflow_id = "whatsapp-" + sender_jid               │
│    handle.signal("new_message", sender, text)           │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 4. Temporal wakes workflow                              │
│    - Loads workflow from database                       │
│    - Replays event history (fast-forward)               │
│    - Executes signal handler                            │
│      @workflow.signal                                   │
│      def new_message(self, sender, text):               │
│          self.pending_messages.append(...)              │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 5. wait_condition returns (condition now true)          │
│    has_message = True                                   │
│    await self._process_messages()                       │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 6. Agent thinking loop                                  │
│    Iteration 1:                                         │
│      - Call LLM: "User wants to check API status"       │
│      - LLM: "I'll curl the endpoint"                    │
│      - Tool call: bash("curl https://api.com/health")   │
│    → Execute bash_executor_activity                     │
│    → Result: "200 OK, response time: 145ms"             │
│                                                          │
│    Iteration 2:                                         │
│      - Call LLM with result                             │
│      - LLM: "API is up! 200 OK, 145ms"                  │
│      - No tool calls → done                             │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 7. Save state to state.md                               │
│    - Conversation history                               │
│    - Metadata (LLM calls, tokens)                       │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 8. Response sent via WhatsApp                           │
│    (In production - would call send_whatsapp activity)  │
│    User sees: "API is up! Status: 200 OK, 145ms"        │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│ 9. Workflow waits again                                 │
│    await workflow.wait_condition(...)                   │
│    → Paused in database until next message              │
└─────────────────────────────────────────────────────────┘
```

**Total time:** ~3-5 seconds from user message to response

---

## System Components

### 1. WhatsApp Listener Service

**Purpose**: Listen for WhatsApp messages via Neonize (Baileys/Whatsmeow) and route them to Temporal workflows.

**Why Neonize (Direct WhatsApp Web Connection):**
- Connects directly as a WhatsApp linked device (like WhatsApp Web)
- Event-driven: receives messages instantly via persistent WebSocket
- Free — no third-party API subscription needed
- Self-chat supported (can message and test with your own number)
- Auth via QR code scan, stored locally in SQLite database

**Responsibilities**:
- Maintain persistent WebSocket connection to WhatsApp
- Receive incoming messages via event callbacks (instant, no polling)
- Parse incoming messages (sender JID, text)
- Route to appropriate Temporal workflow via signal
- Start new workflows if needed (first message in chat)
- Send agent responses back via `client.send_message()`

**Technology**:
- Neonize (Python wrapper around Whatsmeow Go library)
- Temporal Python SDK (for workflow signals)
- SQLite (for WhatsApp auth state persistence)

**Implementation**: See detailed implementation in [WhatsApp Integration](#whatsapp-integration-mvp) section below.

**Note**: For multi-channel support (HTTP, Slack, Email), see `upgrade-ideas.md` for Gateway Service design.

---

### 2. Agent Workflow

**Purpose**: The core orchestration unit representing one agent's execution session.

**Lifecycle**:
```
Start → Load state.md → Enter LLM Loop →
  ┌─→ Get user message (via signal or timer) →
  │   Call LLM activity →
  │   Execute tool activities →
  │   Write state.md →
  │   Send response activity →
  └── (loop until duration limit or stop signal)
→ Graceful shutdown → End
```

**State Variables**:
- `conversation_history`: List of messages
- `current_tools`: Available tools for agent
- `heartbeat_interval`: Minutes between auto-prompts
- `state_file_path`: Path to state.md
- `start_time`: Workflow start timestamp

**Signals**:
- `new_message(sender: str, text: str)`: Add user message to queue
- `stop()`: Graceful shutdown
- `update_heartbeat(interval_minutes: int)`: Change heartbeat frequency

**Queries** (for debugging):
- `get_state()`: Return current conversation state
- `get_uptime()`: How long workflow has been running

---

### 3. Activities

#### 3.1 LLM Call Activity

**Purpose**: Call LLM API with conversation context and get response.

**Input**:
```python
@dataclass
class LLMCallInput:
    messages: List[Message]
    tools: List[ToolDefinition]
    model: str
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 4000
```

**Output**:
```python
@dataclass
class LLMCallOutput:
    """
    Output from LLM API call.

    The tool_calls field is key to the agent loop:
    - If tool_calls is empty/None: LLM is done, task complete
    - If tool_calls has items: LLM wants to execute tools, loop continues

    Modern LLM APIs (OpenAI, Claude) return structured tool calls that we parse
    into this format. The agent loop checks tool_calls to decide whether to
    continue thinking or return the final answer to the user.
    """
    response_text: str  # LLM's text response (thinking, explanation, final answer)
    tool_calls: List[ToolCall]  # Empty = done, Non-empty = needs to execute tools
    usage: TokenUsage  # Token counts for cost tracking
    model_used: str  # Which model was used (for logging/debugging)
```

**Retry Policy**:
- Retry on rate limits, transient errors
- Fallback to different model if primary fails

---

#### 3.2 Bash Executor Activity

**Purpose**: Execute bash commands with safety checks and output capture.

**Input**:
```python
@dataclass
class BashExecuteInput:
    command: str
    working_dir: str
    timeout_seconds: int = 300
    env_vars: Dict[str, str] = None
```

**Output**:
```python
@dataclass
class BashExecuteOutput:
    stdout: str
    stderr: str
    exit_code: int
    execution_time_seconds: float
```

**Safety**:
- Sandboxed execution (Docker or restricted user)
- Timeout enforcement
- Output size limits
- Command validation (no rm -rf /, etc.)

**Heartbeat**:
- For long-running commands, report progress every 10 seconds

---

#### 3.3 State File I/O Activity

**Purpose**: Read/write state.md file for cross-workflow persistence.

**Input**:
```python
@dataclass
class StateFileWriteInput:
    file_path: str
    content: str
    workflow_id: str  # For isolation

@dataclass
class StateFileReadInput:
    file_path: str
    workflow_id: str
```

**Output**:
```python
@dataclass
class StateFileContent:
    content: str
    last_modified: datetime
```

**File Path**: `./state/{workflow_id}/state.md`

---

#### 3.4 Webhook Delivery Activity

**Purpose**: Send messages to external channels (Slack, email, etc.)

**Input**:
```python
@dataclass
class WebhookDeliveryInput:
    channel_type: str  # "slack", "email", "http"
    channel_config: Dict[str, Any]  # API keys, endpoints
    message: str
    metadata: Dict[str, Any] = None
```

**Output**:
```python
@dataclass
class WebhookDeliveryOutput:
    success: bool
    response_code: int
    response_body: str
```

**Retry Policy**:
- Exponential backoff for transient failures
- Immediate failure for 4xx errors (bad config)

---

#### 3.5 Conversation Compaction Activity

**Purpose**: Summarize old conversation history to keep state.md manageable and reduce token costs.

**When**: Triggered automatically when conversation exceeds 100 messages.

**Input**:
```python
@dataclass
class CompactConversationInput:
    messages: List[Message]  # Full conversation history
    keep_first: int = 5      # Keep first N messages for context
    keep_recent: int = 20    # Keep last N messages for continuity
```

**Output**:
```python
@dataclass
class CompactConversationOutput:
    compacted_messages: List[Message]  # First N + summary + last N
    messages_before: int               # Original message count
    messages_after: int                # Compacted message count
    summary_text: str                  # The generated summary
```

**Implementation**:
```python
@activity.defn
async def compact_conversation_activity(input: CompactConversationInput) -> CompactConversationOutput:
    """Compact conversation by summarizing middle messages."""
    messages = input.messages

    if len(messages) <= (input.keep_first + input.keep_recent):
        # Not enough to compact
        return CompactConversationOutput(
            compacted_messages=messages,
            messages_before=len(messages),
            messages_after=len(messages),
            summary_text=""
        )

    # Split conversation
    keep_first = messages[:input.keep_first]
    keep_recent = messages[-input.keep_recent:]
    to_summarize = messages[input.keep_first:-input.keep_recent]

    # Call LLM to summarize middle section
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Format messages for summarization
    conversation_text = "\n\n".join([
        f"[{msg.role.value}]: {msg.content}"
        for msg in to_summarize
    ])

    response = await client.messages.create(
        model="claude-haiku-4.5",  # Fast, cheap model for summarization
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""Summarize this conversation, preserving:
- Key decisions and outcomes
- Important context for future messages
- User preferences
- Unresolved tasks

Conversation ({len(to_summarize)} messages):

{conversation_text}"""
        }]
    )

    summary_text = response.content[0].text

    # Create summary message
    summary_message = Message(
        role=MessageRole.SYSTEM,
        content=f"""[CONVERSATION SUMMARY - {len(to_summarize)} messages]

{summary_text}

[END SUMMARY]""",
        timestamp=datetime.now(timezone.utc)
    )

    # Build compacted conversation: first N + summary + last N
    compacted = keep_first + [summary_message] + keep_recent

    return CompactConversationOutput(
        compacted_messages=compacted,
        messages_before=len(messages),
        messages_after=len(compacted),
        summary_text=summary_text
    )
```

**Benefits**:
- Reduces token costs (fewer messages sent to LLM each call)
- Keeps state.md file manageable
- Preserves important context while removing verbosity
- Automatic - no manual intervention needed

**Example**:
```
Before: 150 messages (75K tokens)
After:  25 messages (12K tokens)
Savings: 62K tokens per LLM call
```

---

#### 3.6 WhatsApp Send Message Activity ⚠️ **CRITICAL FOR MVP**

**Purpose**: Send agent responses back to WhatsApp users via Neonize. This completes the request-response loop.

**Why Critical**: Without this activity, the agent can process messages but cannot send responses back to users!

**Input**:
```python
@dataclass
class WhatsAppSendInput:
    phone_number: str  # User's phone number (digits only, e.g. "1234567890")
    message: str       # Response message to send
```

**Output**:
```python
@dataclass
class WhatsAppSendOutput:
    success: bool
    message_id: str | None    # WhatsApp message ID
    error: str | None         # Error message if failed
```

**Implementation**:
```python
@activity.defn
async def whatsapp_send_message(input: WhatsAppSendInput) -> WhatsAppSendOutput:
    """Send message to WhatsApp user via Neonize.

    The Neonize client is initialized once at worker startup and shared
    across activity calls. It maintains a persistent WebSocket connection
    to WhatsApp, so sends are instant (no HTTP round-trip to a third party).
    """
    try:
        from neonize.utils import build_jid

        # Get the shared neonize client (initialized at worker startup)
        neonize_client = get_neonize_client()

        jid = build_jid(input.phone_number)
        result = neonize_client.send_message(jid, input.message)

        return WhatsAppSendOutput(
            success=True,
            message_id=result.ID,
            error=None
        )

    except Exception as e:
        return WhatsAppSendOutput(
            success=False,
            message_id=None,
            error=f"Failed to send: {str(e)}"
        )
```

**Retry Policy**:
```python
retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    maximum_interval=timedelta(seconds=10),
)
```

**Usage in Workflow**:
```python
@workflow.defn
class AgentWorkflow:
    async def _process_messages(self):
        while self.pending_messages:
            user_msg = self.pending_messages.pop(0)

            # ... agent thinking loop ...

            # After LLM generates final response
            response_text = llm_response.content

            # Send response back to WhatsApp user
            send_result = await workflow.execute_activity(
                whatsapp_send_message,
                WhatsAppSendInput(
                    phone_number=user_msg.sender,
                    message=response_text,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy
            )

            if not send_result.success:
                workflow.logger.error(
                    f"Failed to send WhatsApp message: {send_result.error}"
                )
```

**Error Handling**:
- **Transient errors** (WebSocket disconnect): Neonize auto-reconnects; retry succeeds
- **Permanent errors** (invalid JID): Fail immediately, log error
- **Partial failure**: If send fails after retries, log error but continue workflow

**Common Issues**:
- **Not authenticated**: Must scan QR code on first run (auth persists in neonize.db)
- **Session conflict (440)**: Another device took over the linked session
- **Message too long**: WhatsApp has ~4096 character limit per message

**Testing**:
```python
@pytest.mark.asyncio
async def test_whatsapp_send_message():
    input_data = WhatsAppSendInput(
        phone_number="1234567890",
        message="Hello from agent!",
    )

    result = await whatsapp_send_message(input_data)

    assert result.success is True
    assert result.message_id is not None
    assert result.error is None
```

---

### 4. Worker Configuration

**Purpose**: Execute activities and workflows.

**Worker Pools**:
- **Workflow Worker**: Handles workflow orchestration (lightweight)
- **Activity Worker**: Executes activities (can be resource-intensive)

**Scaling**:
- Run multiple activity workers for parallelism
- Use Temporal task queues to route work

**Task Queues**:
- `agent-workflows`: For agent workflow tasks
- `bash-activities`: For bash execution (can run on specific workers)
- `llm-activities`: For LLM calls
- `io-activities`: For file I/O and state management

---

### 5. Cron Job Manager — DEFERRED (Not MVP)

> **Not needed for MVP.** The WhatsApp listener handles workflow lifecycle automatically. Cron scheduling is useful for autonomous periodic agents (e.g., daily summaries) but not required for conversational use. See `upgrade-ideas.md` for future implementation.

---

### 6. LLM Provider Configuration

**Purpose**: Support multiple LLM API providers with key rotation.

**File**: `llm.py`

**Providers**:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Google (Gemini)
- Local (Ollama, LM Studio)

**Config Structure**:
```python
@dataclass
class LLMProviderConfig:
    provider: str  # "openai", "anthropic", "google", "local"
    model: str
    api_key: str  # Or None for local
    api_base: str = None  # For local endpoints
    max_tokens: int = 4000
    temperature: float = 0.7

class LLMRegistry:
    """Manages multiple LLM providers with fallback."""

    def __init__(self, configs: List[LLMProviderConfig]):
        self.configs = configs
        self.current_index = 0

    def get_client(self) -> LLMClient:
        """Get current LLM client."""
        return create_llm_client(self.configs[self.current_index])

    def rotate(self):
        """Move to next provider."""
        self.current_index = (self.current_index + 1) % len(self.configs)
```

**Usage in Activity**:
```python
async def call_llm_activity(input: LLMCallInput) -> LLMCallOutput:
    registry = get_llm_registry()  # From global config

    for attempt in range(len(registry.configs)):
        try:
            client = registry.get_client()
            response = await client.chat(input.messages, input.tools)
            return LLMCallOutput(...)
        except RateLimitError:
            registry.rotate()
            continue
        except Exception as e:
            raise  # Hard failure

    raise Exception("All LLM providers failed")
```

---

## WhatsApp Integration (MVP)

This section details the complete WhatsApp Listener implementation using **Neonize** — the primary entry point for the MVP.

### Architecture Overview

```
WhatsApp            Neonize Listener           Temporal
────────            ────────────────           ────────

User sends    →     WebSocket event fires  →   Start workflow (first msg)
message             (instant, no polling)      OR Signal workflow (subsequent)
                    Parse sender JID
                    Route to workflow
```

### Bootstrap Flow (How First Workflow Starts)

**Question:** "How does the first workflow start without a gateway?"
**Answer:** The Neonize Listener starts it!

**Complete Flow:**

```
Step 1: First run — scan QR code to link as WhatsApp device
   Neonize displays QR in terminal
   Scan with WhatsApp > Settings > Linked Devices
   Auth saved to neonize.db (persists across restarts)

Step 2: User sends WhatsApp message
   You (or anyone): "Find all TODO comments"

Step 3: Neonize receives message instantly via WebSocket event
   @client.event(MessageEv)
   def on_message(client, message):
       text = message.Message.conversation
       sender = message.Info.MessageSource.Sender.User
       # "1234567890"

Step 4: Listener tries to find existing workflow
   workflow_id = f"whatsapp-{sender}"
   try:
       handle = temporal_client.get_workflow_handle(workflow_id)
       await handle.describe()  # Check if running
   except:
       # This is the FIRST message — start new workflow

Step 5: Listener STARTS new workflow
   handle = await temporal_client.start_workflow(
       AgentWorkflow.run,
       config=WorkflowConfig(...),
       id=f"whatsapp-{sender}"
   )

Step 6: Listener SIGNALS the workflow with message
   await handle.signal("new_message", sender, text)

Step 7: Workflow processes message
   - Loads state.md (empty for first time)
   - Receives signal via new_message handler
   - Processes user message through LLM loop
   - Sends reply via whatsapp_send_message activity
   - Saves state
   - Waits for next message OR heartbeat (30 min)
```

### Listener + Heartbeat Interaction

**Neonize Listener is always connected — no polling interval:**

```python
# Listener: Receives messages instantly via WebSocket events
# (no polling interval — event-driven)

# Workflow: Heartbeat check-in every 30 minutes
heartbeat_interval_minutes = 30
```

**Timeline Example:**

```
10:00:00 - User sends: "Monitor API status"
10:00:00 - Listener receives message instantly (WebSocket event)
10:00:00 - Listener starts new workflow (first message)
10:00:00 - Listener signals workflow
10:00:07 - Workflow processes message, waits (30 min timer starts)

[Listener stays connected, waiting for next event — zero CPU]

10:30:07 - Workflow timeout (30 min passed, no new messages)
10:30:07 - Heartbeat prompt: "Check in and report status"
10:30:12 - LLM: "Monitoring API. 6 checks, all healthy."
10:30:17 - Workflow waits again (new 30 min timer)

11:00:17 - Workflow timeout (heartbeat)
11:00:22 - LLM: "Still monitoring. 12 checks, all healthy."

11:15:00 - User sends: "Any issues?"
11:15:00 - User sends: "Any issues?"
11:15:00 - Listener receives message instantly
11:15:00 - Listener signals EXISTING workflow
11:15:00 - Workflow wakes up (timer canceled)
11:15:02 - Workflow processes new message
11:15:07 - Workflow waits again (new 30 min timer)
```

**Key Points:**
- Listener receives messages instantly (WebSocket events)
- Workflow waits for signals OR timeout (30 min)
- Listener doesn't know about heartbeats
- Workflow doesn't know about the listener
- They're decoupled but work together perfectly!

### Complete Listener Implementation

**File:** `src/whatsapp/listener.py`

```python
import logging
import os
import signal
import threading
from dataclasses import dataclass
from pathlib import Path

from neonize.client import NewClient
from neonize.events import ConnectedEv, MessageEv, PairStatusEv, event
from neonize.utils import log as neonize_log, build_jid
from temporalio.client import Client

from workflows import AgentWorkflow, WorkflowConfig

logger = logging.getLogger(__name__)


@dataclass
class ListenerConfig:
    """Configuration for WhatsApp listener."""
    neonize_db_path: str = "./neonize.db"
    temporal_address: str = "localhost:7233"
    llm_model: str = "claude-sonnet-4.5"
    workflow_max_duration_minutes: int = 60
    my_phone_number: str = ""  # Only process messages from this number


class WhatsAppListener:
    """
    Listens for WhatsApp messages via neonize and routes to Temporal workflows.

    This is the primary entry point for WhatsApp integration (MVP).

    Responsibilities:
    1. Connect to WhatsApp via neonize (WebSocket, linked device)
    2. Listen for incoming messages via event callbacks
    3. Start new workflows (first message in chat)
    4. Signal existing workflows (subsequent messages)
    """

    def __init__(self, config: ListenerConfig):
        self.config = config
        self.client = NewClient(config.neonize_db_path)
        self.temporal_client: Optional[Client] = None

        # Register neonize event handlers
        self.client.event(ConnectedEv)(self._on_connected)
        self.client.event(MessageEv)(self._on_message)
        self.client.event(PairStatusEv)(self._on_pair_status)

    async def start(self):
        """Initialize Temporal client and start neonize listener."""
        logger.info("Starting WhatsApp Listener...")

        # Initialize Temporal client
        self.temporal_client = await Client.connect(
            self.config.temporal_address
        )

        logger.info(f"Connected to Temporal at {self.config.temporal_address}")
        logger.info(f"Auth database: {self.config.neonize_db_path}")

        # Start neonize client (blocks — displays QR on first run)
        # This runs the Go event loop; callbacks fire on message events
        self.client.connect()

    def _on_connected(self, client: NewClient, _: ConnectedEv):
        """Called when WhatsApp connection is established."""
        me = client.get_me()
        logger.info(f"Connected to WhatsApp as {me.JID.User}")

    def _on_pair_status(self, _: NewClient, msg: PairStatusEv):
        """Called after QR code scan — device is now linked."""
        logger.info(f"Linked as {msg.ID.User}")

    def _on_message(self, client: NewClient, message: MessageEv):
        """
        Called on every incoming message — this is the core routing logic.

        Flow:
        1. Extract text from message
        2. Filter: only process messages from our own number
        3. Build deterministic workflow ID from chat
        4. Route to Temporal workflow (start or signal)
        """
        # Extract text content
        text = (
            message.Message.conversation
            or message.Message.extendedTextMessage.text
        )
        if not text:
            return

        sender = message.Info.MessageSource.Sender.User
        is_from_me = message.Info.MessageSource.IsFromMe

        # Only process messages from ourselves (self-chat or our own number)
        # This prevents random people from triggering workflows and consuming LLM tokens.
        if not is_from_me and sender != self.config.my_phone_number:
            logger.debug(f"Ignoring message from {sender} (not in allowed senders)")
            return

        chat_id = message.Info.Chat.User

        logger.info(f"Message from {sender} in chat {chat_id}: {text}")

        # Route to Temporal workflow (run async in event loop)
        asyncio.get_event_loop().run_until_complete(
            self._route_message(
                chat_id=chat_id,
                sender=sender,
                text=text,
            )
        )

    async def _route_message(self, *, chat_id: str, sender: str, text: str):
        """
        Route message to appropriate workflow.

        THIS IS THE KEY METHOD — handles workflow startup!

        Strategy:
        1. Build workflow_id from chat_id (deterministic)
        2. Try to get existing workflow
        3. If found → signal it (existing conversation)
        4. If not found → start new workflow + signal it (new conversation)
        """

        # Build deterministic workflow ID from chat
        workflow_id = f"whatsapp-{chat_id}@c.us"

        try:
            # Try to get existing workflow
            handle = self.temporal_client.get_workflow_handle(workflow_id)

            # Workflow exists! Signal it with new message
            await handle.signal(
                "new_message",
                sender=sender,
                text=text,
            )

            logger.info(f"Signaled existing workflow: {workflow_id}")

        except WorkflowNotFoundError:
            # No workflow exists — this is the FIRST message in this chat!
            logger.info(f"Starting new workflow: {workflow_id}")

            # Create workflow configuration
            # Note: Tools are loaded by the workflow itself (from tools/ directory),
            # not configured by the listener.
            config = WorkflowConfig(
                llm_model=self.config.llm_model,
                max_duration_minutes=self.config.workflow_max_duration_minutes,
                heartbeat_interval_minutes=30,
            )

            # START new workflow
            handle = await self.temporal_client.start_workflow(
                AgentWorkflow.run,
                config,
                id=workflow_id,
                task_queue="agent-tasks",
            )

            logger.info(f"Workflow started: {workflow_id}")

            # Now signal it with the first message
            await handle.signal(
                "new_message",
                sender=sender,
                text=text,
            )

            logger.info(f"Sent first message to new workflow: {workflow_id}")


# ============= Main Entry Point =============

async def main():
    """
    Main entry point for WhatsApp Listener.

    Run this to start the listener!

    First run: displays a QR code — scan with WhatsApp to link.
    Subsequent runs: reconnects automatically (auth in neonize.db).
    """

    # Load configuration from environment
    config = ListenerConfig(
        neonize_db_path=os.getenv("NEONIZE_DB_PATH", "./neonize.db"),
        temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        llm_model=os.getenv("LLM_MODEL", "claude-sonnet-4.5"),
        my_phone_number=os.getenv("MY_PHONE_NUMBER", ""),
    )

    # Create and start listener
    listener = WhatsAppListener(config=config)

    try:
        await listener.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run listener
    asyncio.run(main())
```

### How to Start Everything (MVP Setup)

### Configuration Files

**.env** (root directory)
```bash
# Temporal
TEMPORAL_ADDRESS=localhost:7233

# LLM
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
LLM_MODEL=claude-sonnet-4.5

# Neonize (optional — defaults shown)
NEONIZE_DB_PATH=./neonize.db

# WhatsApp — only process messages from this number (digits only)
MY_PHONE_NUMBER=1234567890

# Workflow
WORKFLOW_MAX_DURATION_MINUTES=60
HEARTBEAT_INTERVAL_MINUTES=30
```

### Production and Development Deployment (Docker Compose)

**docker-compose.yml**
```yaml
version: '3.8'

services:
  temporal:
    image: temporalio/auto-setup:latest
    ports:
      - "7233:7233"  # gRPC
      - "8080:8080"  # UI
    environment:
      - DB=sqlite
      - SQLITE_PRAGMA_journal_mode=WAL
    volumes:
      - ./temporal-data:/etc/temporal

  worker:
    build: .
    command: python -m src.worker
    depends_on:
      - temporal
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./state:/app/state
      - ./workspace:/app/workspace
    restart: unless-stopped

  whatsapp-listener:
    build: .
    command: python -m src.whatsapp.listener
    depends_on:
      - temporal
      - worker
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - LLM_MODEL=claude-sonnet-4.5
      - NEONIZE_DB_PATH=/app/neonize.db
      - MY_PHONE_NUMBER=${MY_PHONE_NUMBER}
    volumes:
      - ./neonize.db:/app/neonize.db  # Persist auth across restarts
    restart: unless-stopped
```


**Start everything with one command:**
```bash
# Create .env file with your credentials
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f whatsapp-listener

# Stop everything
docker-compose down
```

### Debugging & Monitoring

**View Temporal UI:**
```
http://localhost:8080

- See all running workflows
- View workflow history
- Check activity executions
- Debug failures
- Query workflow state
```

**Check Listener Status:**
```bash
# View listener logs
docker-compose logs -f whatsapp-listener

# Or if running locally — neonize logs to stdout
# Look for: "Connected to WhatsApp as ..."
```

**Query Workflow State:**
```python
# From Python
from temporalio.client import Client

client = await Client.connect("localhost:7233")
handle = client.get_workflow_handle("whatsapp-1234567890@c.us")

# Get current state
state = await handle.query("get_state")
print(state)
```

### Common Issues

**Issue: Listener not receiving messages**
```bash
# Check neonize is connected
# Logs should show: "Connected to WhatsApp as <phone>"
# If not connected, delete neonize.db and re-scan QR code

# Check the linked device is still active in WhatsApp:
# WhatsApp → Settings → Linked Devices
```

**Issue: QR code not appearing**
```bash
# Ensure libmagic is installed: brew install libmagic
# Delete neonize.db to force a fresh QR code
rm neonize.db
python -m src.whatsapp.listener
```

**Issue: Workflows not starting**
```bash
# Check Temporal connection
temporal workflow list --address localhost:7233

# Check worker is running
# Should see: "Waiting for tasks..." in worker logs
```

**Issue: No response from agent**
```bash
# Check Temporal UI for errors
# View workflow history
# Check activity failures
```

### Summary

**The WhatsApp Listener:**
- ✅ Connects directly to WhatsApp via neonize (WebSocket)
- ✅ Event-driven — no polling delay
- ✅ Starts workflows automatically (first message)
- ✅ Signals workflows (subsequent messages)
- ✅ Works with heartbeat mechanism
- ✅ No third-party API or gateway needed
- ✅ Free — no subscription costs
- ✅ Supports self-chat (useful for testing)

**To run the MVP:**
1. Start Temporal server
2. Start listener (scan QR on first run)
3. Send WhatsApp message
4. Done!

---

## Error Handling & Retries (MVP)

This section covers basic error handling for the MVP. For advanced strategies, see `upgrade-ideas.md`.

### Philosophy: Resilient by Default

**Key Principles:**
1. **Retry transient errors automatically** (rate limits, network issues)
2. **Fail fast on permanent errors** (bad credentials)
3. **Let LLM handle tool failures** (bash errors, file not found)
4. **Continue workflow despite failures** (don't crash on single error)

### Retry Policies by Activity Type

**1. LLM Calls (Most Critical)**

```python
# Already in plan.md - see _call_llm() method
llm_response = await workflow.execute_activity(
    call_llm_activity,
    input,
    start_to_close_timeout=timedelta(seconds=120),
    retry_policy=RetryPolicy(
        maximum_attempts=3,              # Try 3 times
        initial_interval=timedelta(seconds=1),    # Wait 1s after first failure
        maximum_interval=timedelta(seconds=10),   # Max 10s between retries
        backoff_coefficient=2.0          # Double wait each time (1s→2s→4s)
    )
)
```

**Why:** LLM calls can hit rate limits (common with Claude/GPT). Retry with backoff usually succeeds.

**2. Bash Execution**

```python
bash_result = await workflow.execute_activity(
    bash_executor_activity,
    input,
    start_to_close_timeout=timedelta(seconds=300),
    retry_policy=RetryPolicy(
        maximum_attempts=2,  # Only retry once for bash
        initial_interval=timedelta(seconds=2)
    )
)
```

**Why:** Most bash failures are logic errors (wrong command), not transient. One retry is enough.

**3. File I/O**

```python
state = await workflow.execute_activity(
    read_state_file,
    input,
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(
        maximum_attempts=2,
        initial_interval=timedelta(seconds=1)
    )
)
```

**Why:** File operations usually succeed or fail immediately. Quick retry for race conditions.

### Handling Non-Retriable Errors

**Some errors should NOT be retried:**

```python
@activity.defn
async def call_llm_activity(input: LLMCallInput) -> LLMCallOutput:
    try:
        # Make API call
        response = await client.messages.create(...)
        return LLMCallOutput(...)

    except anthropic.AuthenticationError as e:
        # Bad API key - don't retry!
        raise ApplicationError(
            f"Invalid API key: {e}",
            non_retriable=True  # ← Stop immediately
        )

    except anthropic.RateLimitError as e:
        # Rate limit - retry OK
        logger.warning(f"Rate limited, will retry: {e}")
        raise  # Temporal retries automatically
```

### Let LLM Handle Tool Failures

**Strategy:** Return errors to LLM instead of crashing

```python
async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
    """Execute tool and return result OR error to LLM."""

    try:
        if tool_call.name == "bash":
            output = await workflow.execute_activity(
                bash_executor_activity,
                input,
                retry_policy=RetryPolicy(maximum_attempts=2)
            )

            # Command succeeded?
            if output.exit_code == 0:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    output=output.stdout,
                    success=True
                )
            else:
                # Command failed - return error to LLM
                return ToolResult(
                    tool_call_id=tool_call.id,
                    output=f"Error: {output.stderr}",
                    success=False,
                    error=output.stderr
                )

    except Exception as e:
        # Activity failed - return error to LLM
        return ToolResult(
            tool_call_id=tool_call.id,
            output=f"Tool execution failed: {str(e)}",
            success=False,
            error=str(e)
        )
```

**Result:** LLM sees the error and adapts:

```
User: "Find all Python files"

Iteration 1:
  LLM: bash("find / -name '*.py'")  # Bad: searches from root
  Result: ERROR - "Permission denied"

Iteration 2:
  LLM sees error, tries different approach
  LLM: bash("find . -name '*.py'")  # Good: current directory
  Result: SUCCESS - "app.py\nutils.py"

Iteration 3:
  LLM: "Found 2 Python files" (done)
```

### Worker Resilience

**Q: What happens if a workflow fails after all retries?**

**A: Worker is freed immediately, other workflows continue**

```
Worker handling 4 workflows:
├─ whatsapp-user1 (running)
├─ whatsapp-user2 (running)
├─ whatsapp-user3 (running)
└─ whatsapp-user4 (running)

whatsapp-user1 fails after retries:
├─ Workflow marked as FAILED
├─ Saved to database (can debug later)
├─ Worker slot freed ✅
└─ Worker picks up next task

Worker now handling:
├─ whatsapp-user2 (still running) ✅
├─ whatsapp-user3 (still running) ✅
├─ whatsapp-user4 (still running) ✅
└─ whatsapp-user5 (new task picked up) ✅

Failed workflows don't block workers!
```

### Recovery Strategy

**Failed workflows auto-restart on next message:**

```python
# In WhatsApp listener
async def _route_message(self, *, chat_id, sender, text):
    workflow_id = f"whatsapp-{chat_id}@c.us"

    try:
        # Try to signal existing workflow
        handle = temporal_client.get_workflow_handle(workflow_id)
        await handle.signal("new_message", ...)

    except WorkflowNotFoundError:
        # No workflow (could be failed or terminated)
        # Start new one - conversation continues!
        await temporal_client.start_workflow(
            AgentWorkflow.run,
            config,
            id=workflow_id  # Same ID!
        )
        # Loads state.md - conversation history preserved ✅
```

**User experience:** Seamless! They don't know failure occurred.

### Monitoring with Temporal UI

**View failures:**
1. Open Temporal UI: `http://localhost:8080`
2. Go to Workflows
3. Filter: `ExecutionStatus="Failed"`
4. Click failed workflow to see:
   - Error message
   - Stack trace
   - Which activity failed
   - Retry attempts
   - Full event history

**Reset failed workflow:**
1. Click workflow in UI
2. Click "Reset" button
3. Workflow restarts from beginning
4. Loads state.md (preserved)
5. Continues conversation

### Simple Error Logging

**Activity level:**
```python
@activity.defn
async def bash_executor_activity(input: BashExecuteInput):
    try:
        # Execute command
        ...
    except Exception as e:
        activity.logger.error(f"Bash failed: {input.command} - {e}")
        raise
```

**Workflow level:**
```python
@workflow.run
async def run(self, config):
    try:
        # Main loop
        while not self._should_terminate():
            ...
    except Exception as e:
        workflow.logger.error(f"Workflow error: {e}")
        raise
```

**View logs:**
```bash
# Worker logs
docker-compose logs -f worker

# Or if running locally
tail -f logs/worker.log
```

### What's NOT in MVP (See upgrade-ideas.md)

**Advanced features for later:**
- Circuit breakers (stop calling failing service)
- Dead letter queues (separate queue for failures)
- Automatic alerting (Slack/email on failure)
- Error rate monitoring (track failure %)
- Sophisticated retry strategies (jitter, custom backoff)
- User error notifications (report errors in WhatsApp)

### MVP Error Handling Checklist

For first iteration, just implement:

- ✅ **Retry policies** on all activity calls
- ✅ **Non-retriable errors** for bad credentials
- ✅ **Return tool errors to LLM** (don't crash)
- ✅ **Basic logging** (activity.logger.error)
- ✅ **Monitor in Temporal UI** (check failures)
- ✅ **Auto-restart** (listener starts new workflow on next message)

**Don't worry about:**
- ❌ Complex monitoring systems
- ❌ Alerting infrastructure
- ❌ Sophisticated retry logic
- ❌ Error reporting to users (LLM handles this)

**Keep it simple - Temporal handles most of it!**

---

## File Layout

```
openpaw/
├── docker-compose.yml          # Temporal + Worker setup
├── README.md
├── requirements.txt            # Python dependencies
├── .env.example                # Example environment variables
│
├── src/
│   ├── __init__.py
│   │
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── agent_workflow.py       # Main agent workflow
│   │   └── heartbeat_workflow.py   # Optional: separate heartbeat
│   │
│   ├── activities/
│   │   ├── __init__.py
│   │   ├── llm_call.py             # LLM API activity
│   │   ├── bash_executor.py        # Bash command execution
│   │   ├── state_file_io.py        # state.md read/write
│   │   ├── file_operations.py      # read_file, write_file activities
│   │   ├── conversation_compaction.py  # Conversation summarization
│   │   ├── whatsapp.py             # WhatsApp send message (MVP) ⚠️
│   │   └── webhook_delivery.py     # Slack/email/HTTP delivery (optional)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── messages.py             # Message dataclasses
│   │   ├── tools.py                # Tool definitions
│   │   └── state.py                # State schemas
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── llm.py                  # LLM provider registry
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   ├── google_client.py
│   │   └── local_client.py
│   │
│   ├── whatsapp/                   # WhatsApp Integration (MVP) ⚠️
│   │   ├── __init__.py
│   │   └── listener.py             # Neonize WhatsApp listener
│   │
│   ├── gateway/                    # Optional: Multi-channel support
│   │   ├── __init__.py
│   │   ├── app.py                  # FastAPI app (webhook receiver)
│   │   ├── routes.py               # HTTP routes
│   │   └── signal_sender.py        # Send signals to Temporal
│   │
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── worker.py               # Worker startup script
│   │   └── config.py               # Worker configuration
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging.py              # Logging setup
│   │   ├── config_loader.py        # Load env/config files
│   │   └── state_manager.py        # state.md file helpers
│   │
│   └── cli/
│       ├── __init__.py
│       └── start_workflow.py       # CLI to start workflows
│
├── tests/
│   ├── __init__.py
│   ├── test_workflows/
│   │   └── test_agent_workflow.py
│   ├── test_activities/
│   │   ├── test_bash_executor.py
│   │   └── test_llm_call.py
│   └── test_integration/
│       └── test_end_to_end.py
│
├── config/
│   ├── agent_config.yaml           # Agent configurations
│   └── llm_providers.yaml          # LLM provider configs
│
├── state/                          # Persistent state files
│   └── {workflow_id}/
│       └── state.md
│
├── workspace/                      # Agent workspace files
│   └── {workflow_id}/
│       └── ...                     # Working files
│
├── scripts/
│   ├── setup_temporal.sh           # Setup Temporal cluster
│   ├── start_worker.sh             # Start worker
│   └── deploy.sh                   # Deployment script
│
└── Dockerfile                      # Worker Docker image
```

---

## Data Schemas

### 1. Message Schema

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

@dataclass
class Message:
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For tool responses
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None

@dataclass
class Conversation:
    messages: List[Message]
    workflow_id: str
    created_at: datetime
    updated_at: datetime
```

---

### 2. Tool Schema

**Philosophy**: Tools are defined as markdown files (like OpenClaw) with YAML frontmatter + rich documentation. This makes tools easy to add, human-readable, and provides rich context to the LLM without writing Python code.

#### Markdown-Based Tool Definition (TOOL.md)

Each tool lives in `openpaw/tools/<tool-name>/TOOL.md`:

```markdown
---
name: bash
description: Execute bash commands in a sandboxed container
parameters:
  type: object
  properties:
    command:
      type: string
      description: The bash command to execute
    timeout:
      type: integer
      description: Optional timeout in seconds (default 30)
      default: 30
  required:
    - command
metadata:
  type: cli
  activity: execute_bash_command
  tier: essential
  priority: 1
  retry_policy:
    maximum_attempts: 3
    backoff_coefficient: 2.0
---

# Bash Command Execution

Execute shell commands in a sandboxed environment.

## Usage

Use this tool to run bash commands, install packages, manage files, etc.

## Examples

```bash
# List files
ls -la

# Install a package
pip install requests

# Run a Python script
python analyze.py --input data.csv
```

## Notes

- Commands run in isolated container
- Working directory persists between calls
- Environment variables available: HOME, USER, PATH
- Timeout defaults to 30s, max 300s
```

#### Tool Types

**1. CLI-Backed Tools** (Zero Python Code)

For tools that wrap existing CLI utilities:

```markdown
---
name: web_search
description: Search the web using DuckDuckGo
metadata:
  type: cli
  command_template: "ddgr --json --num {num_results} {query}"
  tier: common
  priority: 2
---
```

**2. Activity-Backed Tools** (Custom Logic)

For tools that need custom Python implementation (API calls, complex logic):

```markdown
---
name: slack_send
description: Send message to Slack channel
metadata:
  type: activity
  activity: slack_send_message_activity
  tier: specialized
  priority: 3
---
```

#### Tool Tiers (Context Management)

To avoid context bloat, tools are organized by tiers:

| Tier | Priority | Examples | Include by Default |
|------|----------|----------|-------------------|
| **essential** | 1-5 | bash, read_file, write_file, python | ✅ Always |
| **common** | 6-15 | web_search, git, calculator, grep | ✅ MVP |
| **specialized** | 16-30 | image_gen, video_edit, database | ❌ On-demand |
| **experimental** | 31+ | custom tools, dev tools | ❌ Manual enable |

**MVP Configuration** (WhatsApp personal use):
- Include: `essential` + `common` tiers
- Total: ~15-20 tools
- Context size: ~8,000 chars (~2,000 tokens)

#### Tool Loader Implementation

```python
# tool_loader.py
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Any

@dataclass
class ToolDefinition:
    name: str
    description: str  # Full markdown content (rich context for LLM)
    parameters: dict[str, Any]
    tool_type: str  # "cli" or "activity"
    activity_name: str | None
    command_template: str | None
    tier: str
    priority: int
    retry_policy: dict[str, Any] | None = None

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic function calling format"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters
        }

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

def load_tools_from_directory(
    tools_dir: Path,
    include_tiers: list[str] = ["essential", "common"],
    max_tools: int = 30,
    max_chars: int = 15_000
) -> list[ToolDefinition]:
    """Load tools with tier-based filtering"""

    tools = []

    for tool_dir in tools_dir.iterdir():
        if not tool_dir.is_dir():
            continue

        tool_md = tool_dir / "TOOL.md"
        if not tool_md.exists():
            continue

        content = tool_md.read_text()

        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            frontmatter = yaml.safe_load(parts[1])
            markdown_content = parts[2].strip()
        else:
            continue  # Invalid format

        # Build full description (frontmatter desc + markdown)
        full_description = f"{frontmatter['description']}\n\n{markdown_content}"

        metadata = frontmatter.get("metadata", {})
        tier = metadata.get("tier", "common")

        # Filter by tier
        if tier not in include_tiers:
            continue

        tool = ToolDefinition(
            name=frontmatter["name"],
            description=full_description,
            parameters=frontmatter["parameters"],
            tool_type=metadata.get("type", "activity"),
            activity_name=metadata.get("activity"),
            command_template=metadata.get("command_template"),
            tier=tier,
            priority=metadata.get("priority", 999),
            retry_policy=metadata.get("retry_policy")
        )

        tools.append(tool)

    # Sort by priority (1 = highest)
    tools.sort(key=lambda t: t.priority)

    # Truncate by count
    tools = tools[:max_tools]

    # Truncate by character count (binary search)
    total_chars = sum(len(t.description) for t in tools)
    if total_chars > max_chars:
        # Binary search for largest subset that fits
        lo, hi = 0, len(tools)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            subset_chars = sum(len(t.description) for t in tools[:mid])
            if subset_chars <= max_chars:
                lo = mid
            else:
                hi = mid - 1
        tools = tools[:lo]

    return tools
```

#### Workflow Integration

```python
# workflows.py
from pathlib import Path
from tool_loader import load_tools_from_directory

# Load tools at module level (happens once when worker starts)
TOOLS_DIR = Path(__file__).parent / "tools"
AVAILABLE_TOOLS = load_tools_from_directory(
    TOOLS_DIR,
    include_tiers=["essential", "common"],  # MVP tiers
    max_tools=30,
    max_chars=15_000
)

# Create mapping from tool name to execution details
TOOL_REGISTRY = {
    tool.name: {
        "type": tool.tool_type,
        "activity": tool.activity_name,
        "command_template": tool.command_template,
        "retry_policy": tool.retry_policy
    }
    for tool in AVAILABLE_TOOLS
}

@workflow.defn
class AgentWorkflow:
    async def _call_llm(self) -> LLMResponse:
        """Call LLM with available tools"""

        # Convert tools to LLM format
        tools_for_llm = [tool.to_anthropic_format() for tool in AVAILABLE_TOOLS]

        llm_input = {
            "messages": self.conversation_history,
            "tools": tools_for_llm,
            "model": "claude-sonnet-4.5-20250929"
        }

        return await workflow.execute_activity(
            call_anthropic_api,
            llm_input,
            start_to_close_timeout=timedelta(minutes=5)
        )

    async def _execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """Execute requested tool calls"""
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["input"]

            # Look up tool details
            tool_info = TOOL_REGISTRY.get(tool_name)
            if not tool_info:
                results.append({
                    "tool_call_id": tool_call["id"],
                    "error": f"Unknown tool: {tool_name}"
                })
                continue

            # Execute based on tool type
            if tool_info["type"] == "cli":
                # CLI-backed: fill template and execute
                command = tool_info["command_template"].format(**tool_args)
                result = await workflow.execute_activity(
                    execute_bash_command,
                    {"command": command},
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=tool_info["retry_policy"]
                )
            else:
                # Activity-backed: call specific activity
                result = await workflow.execute_activity(
                    tool_info["activity"],
                    tool_args,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=tool_info["retry_policy"]
                )

            results.append({
                "tool_call_id": tool_call["id"],
                "output": result
            })

        return results
```

#### Python Data Classes (For Runtime)

```python
# models.py
from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class ToolCall:
    """Tool call requested by LLM"""
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class ToolResult:
    """Result from executing a tool"""
    tool_call_id: str
    output: str
    success: bool
    error: Optional[str] = None
```

#### Example Tools for MVP

**Essential Tier:**
- `bash` - Execute shell commands
- `read_file` - Read file contents
- `write_file` - Write to files
- `python` - Execute Python code

**Common Tier:**
- `web_search` - Search DuckDuckGo
- `git` - Git operations
- `grep` - Search file contents
- `calculator` - Mathematical calculations

#### Benefits

✅ **Easy to add tools** - Just drop TOOL.md file, no Python code
✅ **Rich LLM context** - Full markdown with examples and notes
✅ **No context bloat** - Tier-based filtering keeps prompt small
✅ **Zero-code for CLI tools** - Wrap existing utilities with templates
✅ **Configurable** - User can enable/disable tiers or specific tools
✅ **Human-readable** - Tools are documented in markdown

---

### 3. Workflow State Schema

```python
@dataclass
class AgentWorkflowState:
    workflow_id: str
    conversation: Conversation
    state_file_path: str
    heartbeat_interval_minutes: int
    start_time: datetime
    last_activity_time: datetime

    # Runtime
    pending_messages: List[Message] = field(default_factory=list)
    should_stop: bool = False

    # Stats
    total_llm_calls: int = 0
    total_tool_executions: int = 0
    total_tokens_used: int = 0

@dataclass
class WorkflowConfig:
    max_duration_minutes: int = 60
    heartbeat_interval_minutes: int = 5
    max_conversation_length: int = 100  # Prune old messages
    tools: List[ToolDefinition] = field(default_factory=list)
    llm_model: str = "gpt-4"
    system_prompt: str = "You are a helpful AI assistant."
```

---

### 4. State File Schema (state.md)

**Format**: Markdown with YAML frontmatter

```markdown
---
workflow_id: agent-001
last_updated: 2026-02-28T10:00:00Z
total_runs: 42
last_completed_task: "Analyzed log files"
---

# Agent State

## Memory
- Key insight 1: System uses PostgreSQL for primary database
- Key insight 2: Deployment is on AWS ECS
- Key insight 3: User prefers Python 3.11+

## Ongoing Tasks
- [ ] Investigate database performance issues
- [x] Set up monitoring dashboard
- [ ] Write API documentation

## Recent Actions
- 2026-02-28 09:45: Executed bash command to check disk space
- 2026-02-28 09:30: Searched memory for "database" queries
- 2026-02-28 09:15: Read configuration file

## Notes
This agent is focused on infrastructure monitoring and maintenance.
```

**Parser**:
```python
import yaml
from typing import Dict, Any

def parse_state_file(content: str) -> Dict[str, Any]:
    """Parse state.md into frontmatter and body."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1])
            body = parts[2].strip()
            return {"metadata": frontmatter, "content": body}
    return {"metadata": {}, "content": content}

def serialize_state_file(metadata: Dict[str, Any], content: str) -> str:
    """Serialize to state.md format."""
    yaml_str = yaml.dump(metadata, default_flow_style=False)
    return f"---\n{yaml_str}---\n\n{content}"
```

---

## Pseudo Code Interfaces

### 1. Agent Workflow

```python
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
import asyncio

@workflow.defn
class AgentWorkflow:
    """
    Long-running agent workflow that processes messages and executes tools.
    Runs for a fixed duration, then gracefully shuts down.
    """

    def __init__(self):
        self.state: Optional[AgentWorkflowState] = None
        self.config: Optional[WorkflowConfig] = None
        self.pending_messages: List[Message] = []
        self.should_stop: bool = False

    @workflow.run
    async def run(self, config: WorkflowConfig) -> str:
        """
        Main workflow entry point.

        Args:
            config: Workflow configuration

        Returns:
            Summary of workflow execution
        """
        # Initialize state
        self.config = config
        workflow_id = workflow.info().workflow_id

        # Load state from state.md (if exists)
        state_content = await workflow.execute_activity(
            read_state_file,
            StateFileReadInput(
                file_path=f"./state/{workflow_id}/state.md",
                workflow_id=workflow_id
            ),
            start_to_close_timeout=timedelta(seconds=30)
        )

        self.state = AgentWorkflowState(
            workflow_id=workflow_id,
            conversation=self._load_conversation_from_state(state_content),
            state_file_path=f"./state/{workflow_id}/state.md",
            heartbeat_interval_minutes=config.heartbeat_interval_minutes,
            start_time=workflow.now(),
            last_activity_time=workflow.now()
        )

        # Main loop
        while not self._should_terminate():
            # Wait for message or heartbeat timeout
            has_message = await workflow.wait_condition(
                lambda: len(self.pending_messages) > 0,
                timeout=timedelta(minutes=self.config.heartbeat_interval_minutes)
            )

            if has_message:
                # Process pending messages
                await self._process_messages()
            else:
                # Heartbeat: prompt agent to check in
                await self._heartbeat_prompt()

            # Persist state
            await self._save_state()

        return f"Workflow completed. Total LLM calls: {self.state.total_llm_calls}"

    @workflow.signal
    def new_message(self, sender: str, text: str):
        """Receive new message from external source."""
        msg = Message(
            role=MessageRole.USER,
            content=text,
            metadata={"sender": sender}
        )
        self.pending_messages.append(msg)

    @workflow.signal
    def stop(self):
        """Gracefully stop the workflow."""
        self.should_stop = True

    @workflow.signal
    def update_heartbeat(self, interval_minutes: int):
        """Update heartbeat interval."""
        self.config.heartbeat_interval_minutes = interval_minutes

    @workflow.query
    def get_state(self) -> Dict[str, Any]:
        """Query current state (for debugging)."""
        return {
            "workflow_id": self.state.workflow_id,
            "message_count": len(self.state.conversation.messages),
            "pending_messages": len(self.pending_messages),
            "uptime_minutes": (workflow.now() - self.state.start_time).total_seconds() / 60,
            "total_llm_calls": self.state.total_llm_calls
        }

    # --- Private Methods ---

    async def _process_messages(self):
        """Process all pending messages."""
        while self.pending_messages:
            user_msg = self.pending_messages.pop(0)
            self.state.conversation.messages.append(user_msg)

            # Agent thinking loop - continues until task is complete
            # This allows multi-step reasoning like OpenClaw
            max_iterations = 20  # Safety limit to prevent infinite loops

            for iteration in range(max_iterations):
                # Call LLM with current conversation state
                llm_response = await self._call_llm()
                self.state.total_llm_calls += 1

                # Add LLM's response (thinking + tool calls) to conversation
                self.state.conversation.messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=llm_response.response_text or "",
                        tool_calls=[
                            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                            for tc in llm_response.tool_calls
                        ] if llm_response.tool_calls else None
                    )
                )

                # Check if LLM is done (no tool calls = task complete)
                if not llm_response.tool_calls:
                    # LLM decided it's finished - break the thinking loop
                    break

                # LLM wants to use tools - execute them
                tool_results = await self._execute_tools(llm_response.tool_calls)

                # Add tool results to conversation so LLM can see them
                for result in tool_results:
                    self.state.conversation.messages.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=result.output,
                            tool_call_id=result.tool_call_id,
                            tool_name=result.tool_call_id.split("-")[0]  # Extract tool name
                        )
                    )

                # Loop continues - LLM will see tool results and decide next action
                # Could be: more tools, ask user for input, or final answer

            self.state.last_activity_time = workflow.now()

    async def _call_llm(self) -> LLMCallOutput:
        """Call LLM activity with current conversation."""
        return await workflow.execute_activity(
            call_llm_activity,
            LLMCallInput(
                messages=self.state.conversation.messages[-20:],  # Last 20 messages
                tools=[t.to_openai_format() for t in self.config.tools],
                model=self.config.llm_model,
                api_key="",  # Loaded in activity from env
            ),
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                backoff_coefficient=2.0
            )
        )

    async def _execute_tools(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        """Execute tool calls in parallel."""
        tasks = [
            self._execute_single_tool(tool_call)
            for tool_call in tool_calls
        ]
        return await asyncio.gather(*tasks)

    async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call."""
        self.state.total_tool_executions += 1

        if tool_call.name == "bash":
            output = await workflow.execute_activity(
                bash_executor_activity,
                BashExecuteInput(
                    command=tool_call.arguments["command"],
                    working_dir=f"./workspace/{self.state.workflow_id}",
                    timeout_seconds=tool_call.arguments.get("timeout", 300)
                ),
                start_to_close_timeout=timedelta(seconds=400),
                heartbeat_timeout=timedelta(seconds=30)
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                output=f"stdout: {output.stdout}\nstderr: {output.stderr}\nexit_code: {output.exit_code}",
                success=output.exit_code == 0
            )

        # Add more tool handlers (file_read, file_write, etc.)...

        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            success=False,
            error=f"Unknown tool: {tool_call.name}"
        )

    async def _heartbeat_prompt(self):
        """Inject a heartbeat prompt to keep agent active."""
        heartbeat_msg = Message(
            role=MessageRole.SYSTEM,
            content="[Heartbeat] Check in and report status. Any ongoing tasks or observations?"
        )
        self.pending_messages.append(heartbeat_msg)

    async def _save_state(self):
        """Persist state to state.md file."""
        # Extract key information for state.md
        metadata = {
            "workflow_id": self.state.workflow_id,
            "last_updated": workflow.now().isoformat(),
            "total_runs": self.state.total_llm_calls,
            "total_tokens": self.state.total_tokens_used
        }

        # Build markdown content (simplified)
        content = f"""# Agent State

## Recent Messages
{self._format_recent_messages()}

## Stats
- Total LLM calls: {self.state.total_llm_calls}
- Total tool executions: {self.state.total_tool_executions}
"""

        state_file_content = serialize_state_file(metadata, content)

        await workflow.execute_activity(
            write_state_file,
            StateFileWriteInput(
                file_path=self.state.state_file_path,
                content=state_file_content,
                workflow_id=self.state.workflow_id
            ),
            start_to_close_timeout=timedelta(seconds=30)
        )

        # Simple compaction: If conversation is getting long, summarize old messages
        if len(self.state.conversation.messages) > 100:
            await self._compact_conversation()

    async def _compact_conversation(self):
        """
        Compact conversation by summarizing old messages.

        Strategy (Simple - MVP):
        - Keep first 5 messages (context)
        - Keep last 20 messages (recent conversation)
        - Summarize everything in between
        """
        messages = self.state.conversation.messages

        if len(messages) <= 25:  # Not enough to compact
            return

        workflow.logger.info(f"Compacting {len(messages)} messages")

        # Call compaction activity
        result = await workflow.execute_activity(
            compact_conversation_activity,
            CompactConversationInput(
                messages=messages,
                keep_first=5,
                keep_recent=20
            ),
            start_to_close_timeout=timedelta(seconds=60)
        )

        # Replace with compacted version
        self.state.conversation.messages = result.compacted_messages

        workflow.logger.info(
            f"Compacted: {result.messages_before} → {result.messages_after} messages"
        )

    def _should_terminate(self) -> bool:
        """Check if workflow should terminate."""
        if self.should_stop:
            return True

        # Check duration
        uptime = workflow.now() - self.state.start_time
        if uptime > timedelta(minutes=self.config.max_duration_minutes):
            return True

        return False

    def _format_recent_messages(self) -> str:
        """Format recent messages for state.md."""
        recent = self.state.conversation.messages[-5:]
        return "\n".join([
            f"- {msg.timestamp.strftime('%Y-%m-%d %H:%M')}: [{msg.role.value}] {msg.content[:100]}"
            for msg in recent
        ])

    def _load_conversation_from_state(self, state_content: StateFileContent) -> Conversation:
        """Load conversation from state file."""
        # Parse state.md and reconstruct conversation
        # For simplicity, start fresh each time
        return Conversation(
            messages=[],
            workflow_id=self.state.workflow_id if self.state else "",
            created_at=workflow.now(),
            updated_at=workflow.now()
        )
```

---

### 2. Bash Executor Activity

```python
from temporalio import activity
from temporalio.exceptions import ApplicationError
import subprocess
import asyncio
import os

@activity.defn
async def bash_executor_activity(input: BashExecuteInput) -> BashExecuteOutput:
    """
    Execute bash command with safety checks and output capture.
    Reports heartbeats for long-running commands.
    """
    activity.logger.info(f"Executing command: {input.command}")

    # Validate command (basic safety checks)
    if not _is_command_safe(input.command):
        raise ApplicationError(
            f"Command failed safety check: {input.command}",
            non_retryable=True
        )

    # Set up environment
    env = os.environ.copy()
    if input.env_vars:
        env.update(input.env_vars)

    # Ensure working directory exists
    os.makedirs(input.working_dir, exist_ok=True)

    # Execute command
    start_time = asyncio.get_event_loop().time()

    try:
        process = await asyncio.create_subprocess_shell(
            input.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=input.working_dir,
            env=env
        )

        # Heartbeat loop
        async def heartbeat_loop():
            while True:
                await asyncio.sleep(10)  # Heartbeat every 10 seconds
                activity.heartbeat(f"Command still running: {input.command[:50]}")

        heartbeat_task = asyncio.create_task(heartbeat_loop())

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=input.timeout_seconds
            )
        finally:
            heartbeat_task.cancel()

        exit_code = process.returncode
        execution_time = asyncio.get_event_loop().time() - start_time

        return BashExecuteOutput(
            stdout=stdout.decode('utf-8', errors='replace'),
            stderr=stderr.decode('utf-8', errors='replace'),
            exit_code=exit_code,
            execution_time_seconds=execution_time
        )

    except asyncio.TimeoutError:
        activity.logger.error(f"Command timed out after {input.timeout_seconds}s")
        process.kill()
        raise ApplicationError(
            f"Command timed out after {input.timeout_seconds} seconds",
            non_retryable=True
        )
    except Exception as e:
        activity.logger.error(f"Command execution failed: {e}")
        raise


def _is_command_safe(command: str) -> bool:
    """Basic safety checks for commands."""
    dangerous_patterns = [
        "rm -rf /",
        "dd if=",
        "mkfs",
        "> /dev/sda",
        ":(){ :|:& };:",  # Fork bomb
    ]

    for pattern in dangerous_patterns:
        if pattern in command:
            return False

    return True
```

---

### 3. LLM Call Activity

```python
from temporalio import activity
from temporalio.exceptions import ApplicationError
import openai
import anthropic
from typing import List

@activity.defn
async def call_llm_activity(input: LLMCallInput) -> LLMCallOutput:
    """
    Call LLM API with retry logic and provider fallback.
    """
    activity.logger.info(f"Calling LLM: {input.model}")

    # Get LLM client based on model
    if input.model.startswith("gpt"):
        return await _call_openai(input)
    elif input.model.startswith("claude"):
        return await _call_anthropic(input)
    else:
        raise ApplicationError(f"Unsupported model: {input.model}", non_retryable=True)


async def _call_openai(input: LLMCallInput) -> LLMCallOutput:
    """Call OpenAI API."""
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = await client.chat.completions.create(
            model=input.model,
            messages=[{"role": m.role.value, "content": m.content} for m in input.messages],
            tools=input.tools if input.tools else None,
            temperature=input.temperature,
            max_tokens=input.max_tokens
        )

        message = response.choices[0].message

        # Parse tool calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                ))

        return LLMCallOutput(
            response_text=message.content or "",
            tool_calls=tool_calls,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            ),
            model_used=response.model
        )

    except openai.RateLimitError as e:
        activity.logger.warning(f"Rate limit hit: {e}")
        raise  # Let Temporal retry
    except openai.APIError as e:
        activity.logger.error(f"OpenAI API error: {e}")
        raise


async def _call_anthropic(input: LLMCallInput) -> LLMCallOutput:
    """Call Anthropic API."""
    # Similar implementation for Claude
    # ... (omitted for brevity)
    pass
```

---

### 4. Gateway Service (FastAPI)

Note Gateway is not part of MVP. 

```python
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from temporalio.client import Client
import os

app = FastAPI()

# Temporal client (initialized on startup)
temporal_client: Client = None


class IncomingMessage(BaseModel):
    workflow_id: str
    sender: str
    text: str


@app.on_event("startup")
async def startup():
    global temporal_client
    temporal_client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "localhost:7233"))


@app.post("/webhook/slack")
async def slack_webhook(request: Request):
    """Receive Slack webhook and forward to agent workflow."""
    data = await request.json()

    # Parse Slack event
    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}

    event = data.get("event", {})
    if event.get("type") == "message":
        text = event.get("text", "")
        user = event.get("user", "unknown")
        channel = event.get("channel", "")

        # Determine workflow ID (could be based on channel)
        workflow_id = f"agent-{channel}"

        # Send signal to workflow
        handle = temporal_client.get_workflow_handle(workflow_id)
        await handle.signal("new_message", user, text)

        return {"status": "ok"}

    return {"status": "ignored"}


@app.post("/message")
async def send_message(message: IncomingMessage):
    """Generic endpoint to send message to agent."""
    try:
        handle = temporal_client.get_workflow_handle(message.workflow_id)
        await handle.signal("new_message", message.sender, message.text)
        return {"status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Query workflow state."""
    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        state = await handle.query("get_state")
        return state
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### 5. Parallelization Strategy (MVP) ⚡

**Philosophy**: Simple parallel execution where safe, sequential where dependencies exist.

#### Tool Execution Parallelization

**When LLM requests multiple tools**, execute them in parallel for better performance:

```python
async def _execute_tools(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
    """
    Execute multiple tools in parallel using asyncio.gather.

    Performance: 3 tools @ 2s each = 2s total (not 6s sequential)
    """

    # Create tasks for all tool executions
    tasks = [
        self._execute_single_tool(tool_call)
        for tool_call in tool_calls
    ]

    # Execute all in parallel, capture exceptions
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Format results, handle failures gracefully
    formatted_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # Tool execution failed - return error to LLM
            formatted_results.append(ToolResult(
                tool_call_id=tool_calls[i].id,
                output=f"Error executing tool: {str(result)}",
                success=False,
                error=str(result)
            ))
        else:
            formatted_results.append(result)

    return formatted_results


async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
    """
    Execute a single tool (called in parallel by _execute_tools).

    This method routes to the appropriate activity based on tool type.
    """
    tool_info = TOOL_REGISTRY.get(tool_call.name)

    if not tool_info:
        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            success=False,
            error=f"Unknown tool: {tool_call.name}"
        )

    try:
        if tool_info["type"] == "cli":
            # CLI-backed tool: fill template and execute
            command = tool_info["command_template"].format(**tool_call.arguments)
            result = await workflow.execute_activity(
                execute_bash_command,
                {"command": command, "timeout": tool_call.arguments.get("timeout", 30)},
                start_to_close_timeout=timedelta(seconds=tool_call.arguments.get("timeout", 30) + 10),
                retry_policy=tool_info["retry_policy"]
            )

            return ToolResult(
                tool_call_id=tool_call.id,
                output=result.get("stdout", ""),
                success=result.get("exit_code") == 0,
                error=result.get("stderr") if result.get("exit_code") != 0 else None
            )

        else:
            # Activity-backed tool: call specific activity
            result = await workflow.execute_activity(
                tool_info["activity"],
                tool_call.arguments,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=tool_info["retry_policy"]
            )

            return ToolResult(
                tool_call_id=tool_call.id,
                output=result.get("content", str(result)),
                success=result.get("success", True),
                error=result.get("error")
            )

    except Exception as e:
        # Activity execution failed - let LLM know
        return ToolResult(
            tool_call_id=tool_call.id,
            output="",
            success=False,
            error=f"Tool execution failed: {str(e)}"
        )
```

#### When Parallel Execution is Safe

**Parallel-safe scenarios** (execute concurrently):
- ✅ Read-only operations: `bash("ls")`, `read_file()`, `grep()`, `web_search()`
- ✅ Independent writes: Writing to different files
- ✅ Idempotent operations: Can be run multiple times safely

**Requires sequential** (LLM handles this):
- Dependencies: Tool B needs Tool A's output
- Same resource: Writing to the same file
- Order-sensitive: Database transactions

**How LLM handles dependencies:**
```
User: "Create a directory and write a file in it"

LLM Request 1:
  tool_calls: [{"name": "bash", "input": {"command": "mkdir data"}}]

(Wait for result...)

LLM Request 2:
  tool_calls: [{"name": "write_file", "input": {"path": "data/output.txt", ...}}]
```

The LLM naturally makes sequential requests when tools depend on each other!

#### Multiple Workflows (Automatic)

**Temporal automatically parallelizes workflows:**

```
User A (WhatsApp) → Workflow: whatsapp-userA
User B (WhatsApp) → Workflow: whatsapp-userB
User C (WhatsApp) → Workflow: whatsapp-userC

All run concurrently, isolated state ✅
```

**No code needed** - Temporal handles this automatically!

#### Worker Configuration (MVP)

```python
# worker.py
async def main():
    """Start worker with sensible concurrency limits for MVP"""

    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="agent-tasks",
        workflows=[AgentWorkflow],
        activities=[
            call_anthropic_api,
            execute_bash_command,
            read_file_activity,
            write_file_activity,
            read_state_file,
            write_state_file,
            compact_conversation_activity,
            whatsapp_send_message
        ],
        max_concurrent_workflow_tasks=100,   # Many workflows (100 chats)
        max_concurrent_activities=20,        # Reasonable activity concurrency
        max_concurrent_workflow_task_polls=5,
        max_concurrent_activity_task_polls=5
    )

    print("Worker started")
    print("- Max concurrent workflows: 100")
    print("- Max concurrent activities: 20")
    print("- Tool execution: Parallel via asyncio.gather")

    await worker.run()
```

#### Performance Benefits

**Sequential tool execution:**
```
Tool 1: bash("ls")           [0s--------2s]
Tool 2: read_file("app.py")              [2s--------4s]
Tool 3: grep("TODO", ".")                            [4s--------6s]
Total: 6 seconds
```

**Parallel tool execution:**
```
Tool 1: bash("ls")           [0s--------2s]
Tool 2: read_file("app.py")  [0s--------2s]
Tool 3: grep("TODO", ".")    [0s--------2s]
Total: 2 seconds (3x faster!)
```

**MVP Performance:**
- ⚡ **3x+ faster** tool execution (parallel)
- 🔄 **10-20 concurrent WhatsApp chats** (automatic)
- 📈 **20 concurrent activity executions** (worker config)

#### What's NOT in MVP (See upgrade-ideas.md)

- ❌ Multiple workers (single worker sufficient for MVP)
- ❌ Task queue separation (single queue is fine)
- ❌ Advanced worker scaling
- ❌ Load balancing across worker pools

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

**Goals**: Set up Temporal infrastructure and basic workflow

**Tasks**:
1. **Docker Compose Setup**
   - Temporal server
   - Temporal UI
   - PostgreSQL (for Temporal)
   - Worker container

2. **Project Structure**
   - Initialize Python project
   - Set up dependencies (temporalio, openai, etc.)
   - Create directory structure

3. **Basic Agent Workflow**
   - Implement `AgentWorkflow` with simple message loop
   - No tools yet, just echo messages back
   - Test workflow start/stop via CLI

4. **State File I/O Activity**
   - Implement `read_state_file` and `write_state_file` activities
   - Create `state.md` parser
   - Test persistence across workflow restarts

**Deliverables**:
- Working Docker Compose setup
- Basic workflow that can receive signals
- State persistence working

---

### Phase 2: LLM Integration (Week 2)

**Goals**: Integrate LLM and basic tool execution

**Tasks**:
1. **LLM Provider Configuration**
   - Implement `llm.py` with OpenAI/Anthropic/Google clients
   - API key management via environment variables
   - Basic retry logic

2. **LLM Call Activity**
   - Implement `call_llm_activity`
   - Handle streaming responses (optional)
   - Parse tool calls from LLM response

3. **Tool System (MVP Tools)**
   - Load tools from `tools/` directory (TOOL.md files)
   - Implement tool loader with tier-based filtering
   - Essential tools: bash, read_file, write_file, python
   - Common tools: web_search, git, grep, calculator

4. **Core Activities**
   - `bash_executor_activity` - Execute bash (handles 6 CLI tools)
   - `read_file_activity` - Read file contents
   - `write_file_activity` - Write file contents
   - Safety checks and heartbeat reporting

**Deliverables**:
- Agent can call LLM and get responses
- Tool loader working (loads 8 MVP tools)
- All essential + common tools working
- Basic conversation flow

**Testing**:
- Unit tests for LLM clients
- Unit tests for each activity
- Integration test: send message → LLM responds → execute bash tool
- Tool test: verify all 8 MVP tools work

---

### Phase 3: WhatsApp Integration & Signals (Week 3) ⚠️ **MVP CRITICAL**

**Goals**: Enable WhatsApp messaging and complete request-response loop

**Tasks**:
1. **Signal Handling**
   - Implement `new_message` signal
   - Implement `stop` and `update_heartbeat` signals
   - Test signal delivery

2. **WhatsApp Activities (MVP)** ⚠️ **REQUIRED**
   - Implement `whatsapp_send_message` activity (neonize)
   - Test sending messages back to users
   - Handle message formatting and errors

3. **WhatsApp Listener Service (MVP)** ⚠️ **REQUIRED**
   - Connect to WhatsApp via neonize (WebSocket, linked device)
   - Listen for incoming messages via event callbacks
   - Start workflows for new chats
   - Signal existing workflows for ongoing chats

4. **Heartbeat Mechanism**
   - Implement heartbeat timer in workflow
   - Configurable heartbeat prompts
   - Test periodic prompts

**Deliverables**:
- WhatsApp Listener receiving messages via neonize
- `whatsapp_send_message` activity working
- Complete loop: Receive WhatsApp → Process → Respond to WhatsApp
- Signals triggering workflow actions
- Heartbeat working

**Testing**:
- End-to-end test: Send WhatsApp message → workflow processes → receive response
- Heartbeat test: verify agent prompts itself every X minutes
- Error test: neonize disconnected → graceful reconnection

**Optional (defer to upgrade-ideas.md)**:
- Gateway Service (multi-channel support)
- Slack/Email integration

---

### Phase 4: Advanced Tools and State Management (Week 4)

**Goals**: Add additional tools and improve state persistence

**Tasks**:
1. **State Management Improvements**
   - Implement `state_manager.py` with section-based updates
   - Add state.md summarization (to keep file size manageable)
   - Test state persistence across workflow restarts

2. **Additional Tools**
   - File read/write activities
   - Webhook delivery activity (Slack, email)
   - HTTP request tool

3. **Tool Execution Optimization**
   - Parallel tool execution
   - Timeout handling
   - Error recovery

**Deliverables**:
- State manager working with section updates
- File tools working
- Webhook delivery working

**Testing**:
- State persistence test: restart workflow, verify memory retained
- File tool test: write file, read back, verify content
- Webhook test: send Slack message

---

### Phase 5: Cron and Scheduling — DEFERRED (Not MVP)

> **Moved out of MVP.** The WhatsApp listener handles workflow lifecycle (start on first message, signal on subsequent messages, restart on next message after expiry). Cron scheduling is useful for autonomous periodic agents but not needed for the conversational MVP. See `upgrade-ideas.md` for details.

**Deferred Tasks**:
- Temporal Cron Workflows
- Workflow Duration Management (auto-restart on schedule)
- Cron Job Configuration (YAML config, CLI)

---

### Phase 6: Multi-Agent and Routing (Week 6)

**Goals**: Support multiple concurrent agents with routing

**Tasks**:
1. **Workflow Isolation**
   - Separate state directories per workflow
   - Separate workspaces per workflow
   - Test concurrent workflows

2. **Message Routing**
   - Route incoming messages to correct workflow based on channel/user
   - Auto-start workflows if not running
   - Load balancing (optional)

3. **Agent Configuration**
   - YAML config for multiple agents
   - Different tools per agent
   - Different system prompts per agent

**Deliverables**:
- Multiple agents running concurrently
- Message routing working
- Agent-specific configuration

**Testing**:
- Multi-agent test: start 3 agents, send messages to each, verify isolation
- Routing test: send message to channel, verify routed to correct agent

---

### Phase 7: Testing and Hardening (Week 7)

**Goals**: Comprehensive testing and error handling

**Tasks**:
1. **Unit Tests**
   - All activities tested
   - All workflows tested
   - All tools tested

2. **Integration Tests**
   - End-to-end scenarios
   - Failure recovery scenarios
   - Performance tests

3. **Error Handling**
   - Activity retry policies tuned
   - Graceful degradation on API failures
   - Logging and monitoring

4. **Documentation**
   - API documentation
   - Deployment guide
   - User guide

**Deliverables**:
- 80%+ test coverage
- All integration tests passing
- Complete documentation

---

### Phase 8: Deployment (Week 8)

**Goals**: Deploy to production environment

**Tasks**:
1. **Docker Images**
   - Build worker image
   - Build gateway image
   - Optimize for size/performance

2. **Docker Compose Production Config**
   - Environment variables
   - Volume mounts
   - Health checks
   - Resource limits

3. **Monitoring**
   - Temporal UI access
   - Application logs
   - Metrics (optional: Prometheus/Grafana)

4. **Deployment**
   - Deploy to server
   - Test in production
   - Monitor for issues

**Deliverables**:
- Production-ready deployment
- Monitoring setup
- Runbooks for common issues

---

## Testing Strategy

### Unit Testing

**Tools**: pytest, pytest-asyncio

**Coverage Areas**:
1. **Activities**
   - Mock Temporal context
   - Test each activity in isolation
   - Test error cases (timeouts, API failures)

   Example:
   ```python
   @pytest.mark.asyncio
   async def test_bash_executor_success():
       input = BashExecuteInput(
           command="echo 'hello world'",
           working_dir="/tmp",
           timeout_seconds=10
       )
       output = await bash_executor_activity(input)
       assert output.exit_code == 0
       assert "hello world" in output.stdout
   ```

2. **LLM Clients**
   - Mock API responses
   - Test parsing logic
   - Test retry logic

3. **Tool Definitions**
   - Test schema validation
   - Test OpenAI format conversion

---

### Integration Testing

**Tools**: pytest with Temporal test server

**Coverage Areas**:
1. **Workflow End-to-End**
   - Start workflow
   - Send signals
   - Execute activities
   - Verify state changes

   Example:
   ```python
   @pytest.mark.asyncio
   async def test_agent_workflow_message_handling():
       async with await WorkflowEnvironment.start_time_skipping() as env:
           async with Worker(
               env.client,
               task_queue="test-queue",
               workflows=[AgentWorkflow],
               activities=[call_llm_activity, bash_executor_activity]
           ):
               # Start workflow
               handle = await env.client.start_workflow(
                   AgentWorkflow.run,
                   WorkflowConfig(...),
                   id="test-agent-1",
                   task_queue="test-queue"
               )

               # Send message signal
               await handle.signal("new_message", "user1", "hello")

               # Wait for processing
               await asyncio.sleep(1)

               # Query state
               state = await handle.query("get_state")
               assert state["message_count"] > 0
   ```

2. **Gateway Integration**
   - Test webhook reception
   - Test signal delivery to workflow
   - Test query responses

3. **State Persistence**
   - Write to state.md
   - Restart workflow
   - Verify state retained across restarts

---

### Smoke Testing

**Purpose**: Quick sanity check after deployment

**Tests**:
1. Start a workflow via CLI
2. Send a message via webhook
3. Verify LLM response received
4. Execute a bash command
5. Query workflow state
6. Stop workflow

**Script**:
```bash
#!/bin/bash
set -e

echo "Starting workflow..."
python -m src.cli.start_workflow --workflow-id smoke-test-1

echo "Sending message..."
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"workflow_id": "smoke-test-1", "sender": "tester", "text": "run: echo hello"}'

sleep 5

echo "Querying state..."
curl http://localhost:8000/status/smoke-test-1

echo "Stopping workflow..."
# Send stop signal

echo "Smoke test passed!"
```

---

### Performance Testing

**Tools**: locust, artillery

**Scenarios**:
1. **Load Test**
   - 100 concurrent workflows
   - 1000 messages/minute
   - Measure latency, throughput

2. **Stress Test**
   - Gradually increase load until failure
   - Identify bottlenecks

3. **Soak Test**
   - Run for 24 hours
   - Check for memory leaks
   - Check for resource exhaustion

---

### Failure Recovery Testing

**Scenarios**:
1. **Worker Crash**
   - Kill worker mid-execution
   - Verify workflow resumes on restart

2. **Activity Timeout**
   - Simulate long-running activity
   - Verify timeout handling

3. **API Failure**
   - Mock LLM API failures
   - Verify retry and fallback

4. **Network Partition**
   - Simulate network issues
   - Verify eventual consistency

---

## Deployment & Docker Compose

### Deployment Strategy Overview

**Critical Concept**: `state.md` files MUST be shared across all workers!

```
┌──────────────────────────────────────────────────────┐
│                 Shared Storage                        │
│  ┌─────────────────────────────────────────────┐    │
│  │ state/                                       │    │
│  │  └── whatsapp-user1/state.md ◄──────┬──────┤    │
│  │  └── whatsapp-user2/state.md ◄──┐   │      │    │
│  │  └── whatsapp-user3/state.md ◄┐ │   │      │    │
│  └────────────────────────────────┼─┼───┼──────┘    │
│                                   │ │   │           │
│  ┌────────┐  ┌────────┐  ┌────────┼─┼───┼─────┐    │
│  │Worker 1│  │Worker 2│  │Worker 3│ │   │     │    │
│  │ Reads──┘  │ Writes─┘  │ Reads──┘ │   │     │    │
│  └────────┘  └────────┘  └──────────┘   │     │    │
│                                          │     │    │
│  ┌─────────────────┐  ┌─────────────────┼─────┘    │
│  │ WhatsApp Listener│  │ Temporal Server │          │
│  │   Writes─────────┘  └─────────────────┘          │
│  └──────────────────┘                                │
└──────────────────────────────────────────────────────┘
```

**Deployment Options:**
1. **Docker Compose (Single Host)**: Named volumes (automatic sharing)
2. **Docker Compose (Multi-Host)**: NFS/Samba mount
3. **Kubernetes**: PersistentVolumeClaim with ReadWriteMany (NFS, EFS, etc.)

---

### Docker Compose Files

#### 1. `docker-compose.yml` (Base / Production) ⚠️ **USER-FACING**

**Purpose**: Minimal, production-ready setup for end users

```yaml
version: '3.8'

services:
  # Temporal Server
  temporal:
    image: temporalio/auto-setup:latest
    container_name: temporal
    ports:
      - "7233:7233"  # gRPC API
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgresql
    depends_on:
      postgresql:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "tctl", "--address", "localhost:7233", "cluster", "health"]
      interval: 5s
      timeout: 5s
      retries: 10

  # Temporal UI (Optional - can disable for production)
  temporal-ui:
    image: temporalio/ui:latest
    container_name: temporal-ui
    ports:
      - "8080:8080"
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - TEMPORAL_CORS_ORIGINS=http://localhost:3000
    depends_on:
      temporal:
        condition: service_healthy

  # PostgreSQL for Temporal
  postgresql:
    image: postgres:15-alpine
    container_name: temporal-postgres
    environment:
      - POSTGRES_USER=temporal
      - POSTGRES_PASSWORD=temporal
      - POSTGRES_DB=temporal
    volumes:
      - temporal-postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U temporal"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Worker (Handles workflows and activities)
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: openpaw-worker
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LLM_MODEL=${LLM_MODEL:-claude-sonnet-4.5-20250929}
    volumes:
      # ⚠️ CRITICAL: Local bind mounts for easy access to state.md files
      - ./state:/app/state               # state.md files (visible on host!)
      - ./workspace:/app/workspace       # Working files
      - ./tools:/app/tools:ro            # Tool definitions (read-only)
    depends_on:
      temporal:
        condition: service_healthy
    command: python -m src.worker
    restart: unless-stopped

  # WhatsApp Listener (MVP Entry Point)
  whatsapp-listener:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: whatsapp-listener
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - LLM_MODEL=${LLM_MODEL:-claude-sonnet-4.5-20250929}
      - NEONIZE_DB_PATH=/app/neonize.db
      - MY_PHONE_NUMBER=${MY_PHONE_NUMBER}
    volumes:
      - ./neonize.db:/app/neonize.db  # Persist auth across restarts
    depends_on:
      temporal:
        condition: service_healthy
      worker:
        condition: service_started
    command: python -m src.whatsapp.listener
    restart: unless-stopped

# ⚠️ CRITICAL: Named volume for PostgreSQL only
# State/workspace use local bind mounts so you can view state.md files directly!
volumes:
  temporal-postgres-data:
    driver: local

networks:
  default:
    name: openpaw-network
```

**Start Production:**
```bash
# Copy example env file
cp .env.example .env

# Edit with your API keys
nano .env

# Create local directories for state/workspace
mkdir -p state workspace tools

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f worker whatsapp-listener

# Scale workers (all share same volumes!)
docker-compose up -d --scale worker=3

# 🎉 View state.md files directly on your host machine!
ls -la state/
cat state/whatsapp-<phone>/state.md
```

**Benefits of Local Bind Mounts:**
- ✅ View `state.md` files directly: `cat ./state/whatsapp-123456/state.md`
- ✅ Edit workspace files with your IDE
- ✅ Debug tool definitions by reading `./tools/*/TOOL.md`
- ✅ No need for `docker exec` or `docker volume inspect`
- ✅ State persists even if containers are removed

---

#### 2. `docker-compose.dev.yml` (Development Overrides)

**Purpose**: Hot reload, test containers, debugging tools

```yaml
version: '3.8'

services:
  # Override worker for development
  worker:
    build:
      context: .
      dockerfile: Dockerfile.dev  # Dev image with hot reload
    volumes:
      # Mount source code for hot reload
      - ./src:/app/src:ro
      - ./tools:/app/tools:ro
      - ./config:/app/config:ro
      # Local bind mounts (same as production)
      - ./state:/app/state
      - ./workspace:/app/workspace
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - PYTHONUNBUFFERED=1
      - LOG_LEVEL=DEBUG
    command: >
      sh -c "pip install watchdog &&
             watchmedo auto-restart --recursive --pattern='*.py' --directory=./src
             -- python -m src.worker"

  # Override listener for development
  whatsapp-listener:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - ./src:/app/src:ro
      - ./neonize.db:/app/neonize.db
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - LLM_MODEL=${LLM_MODEL:-claude-sonnet-4.5-20250929}
      - NEONIZE_DB_PATH=/app/neonize.db
      - LOG_LEVEL=DEBUG
    command: >
      sh -c "pip install watchdog &&
             watchmedo auto-restart --recursive --pattern='*.py' --directory=./src
             -- python -m src.whatsapp.listener"

  # Add pytest container for testing
  pytest:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - ./src:/app/src:ro
      - ./tests:/app/tests:ro
      - ./tools:/app/tools:ro
      - ./state:/app/state
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - PYTEST_ARGS=${PYTEST_ARGS:--v}
    command: pytest ${PYTEST_ARGS}
    profiles:
      - test  # Only start with: --profile test

  # Redis for caching (dev only)
  redis:
    image: redis:7-alpine
    container_name: redis-dev
    ports:
      - "6379:6379"
```

**Start Development:**
```bash
# Start with dev overrides (hot reload!)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Run tests
docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pytest

# Start with specific profile
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile test up
```

---

#### 3. `docker-compose.test.yml` (Testing Overrides)

**Purpose**: Automated testing, CI/CD

```yaml
version: '3.8'

services:
  # Use test database (ephemeral)
  postgresql:
    environment:
      - POSTGRES_USER=temporal_test
      - POSTGRES_PASSWORD=temporal_test
      - POSTGRES_DB=temporal_test
    tmpfs:
      - /var/lib/postgresql/data  # In-memory DB for speed

  # Test worker with mocked activities
  worker:
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - ANTHROPIC_API_KEY=test-key-mock
      - MOCK_LLM_RESPONSES=true
      - LOG_LEVEL=INFO
    command: python -m src.worker --test-mode

  # Don't start listener in test mode
  whatsapp-listener:
    profiles:
      - manual  # Skip auto-start

  # Test runner
  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - ./src:/app/src:ro
      - ./tests:/app/tests:ro
      - ./tools:/app/tools:ro
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
    command: >
      sh -c "pytest tests/ -v --cov=src --cov-report=xml --cov-report=term &&
             echo 'All tests passed!'"
    depends_on:
      temporal:
        condition: service_healthy
```

**Run Tests:**
```bash
# Run full test suite
docker-compose -f docker-compose.yml -f docker-compose.test.yml up --abort-on-container-exit

# CI/CD usage
docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-runner
```

---

### Multi-Host Docker Compose (NFS)

**For multiple Docker hosts sharing state:**

```yaml
# docker-compose.yml (add NFS volume)
volumes:
  agent-state:
    driver: local
    driver_opts:
      type: nfs
      o: addr=192.168.1.100,rw,nfsvers=4
      device: ":/mnt/openpaw/state"

  agent-workspace:
    driver: local
    driver_opts:
      type: nfs
      o: addr=192.168.1.100,rw,nfsvers=4
      device: ":/mnt/openpaw/workspace"
```

**NFS Server Setup:**
```bash
# On NFS server (Ubuntu/Debian)
sudo apt-get install nfs-kernel-server

# Create directories
sudo mkdir -p /mnt/openpaw/{state,workspace}
sudo chown -R nobody:nogroup /mnt/openpaw

# Configure exports
echo "/mnt/openpaw *(rw,sync,no_subtree_check,no_root_squash)" | sudo tee -a /etc/exports

# Restart NFS
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
```

---

> **Note**: Kubernetes deployment with multi-node support is covered in `upgrade-ideas.md` Section 12. The MVP uses Docker Compose which is sufficient for single-host deployments.

---

### Dockerfiles

#### `Dockerfile` (Production)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY tools/ ./tools/
COPY config/ ./config/

# Create directories (volumes will mount here)
RUN mkdir -p /app/state /app/workspace

# Non-root user for security
RUN useradd -m -u 1000 openpaw && \
    chown -R openpaw:openpaw /app
USER openpaw

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys; sys.exit(0)"

# Default command (override in docker-compose)
CMD ["python", "-m", "src.worker"]
```

#### `Dockerfile.dev` (Development with Hot Reload)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies + dev tools
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ffmpeg \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dev dependencies
RUN pip install --no-cache-dir \
    watchdog \
    black \
    ruff \
    mypy \
    pytest \
    pytest-asyncio \
    pytest-cov \
    ipdb

# Create directories
RUN mkdir -p /app/state /app/workspace /app/src /app/tools /app/config

# Don't copy code (will be mounted as volume for hot reload)

# Run as root in dev for easier debugging
# USER openpaw

# Default command (override in docker-compose.dev.yml)
CMD ["python", "-m", "src.worker"]
```

---

---

### Requirements.txt

```txt
# Temporal
temporalio>=1.5.0

# LLM Providers
openai>=1.0.0
anthropic>=0.18.0
google-generativeai>=0.3.0

# Gateway
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.5.0

# Utilities
pyyaml>=6.0
python-dotenv>=1.0.0
httpx>=0.26.0
aiofiles>=23.2.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0

# Development
black>=23.12.0
ruff>=0.1.0
mypy>=1.8.0
```

---

### Environment Variables

#### `.env.example` (Copy to `.env`)

```bash
# Temporal Connection
TEMPORAL_ADDRESS=localhost:7233

# LLM Configuration
ANTHROPIC_API_KEY=sk-ant-your-key-here
LLM_MODEL=claude-sonnet-4.5-20250929

# WhatsApp (Neonize)
NEONIZE_DB_PATH=./neonize.db
MY_PHONE_NUMBER=1234567890  # Only process messages from this number (digits only)

# Workflow Configuration
DEFAULT_WORKFLOW_DURATION_MINUTES=60
DEFAULT_HEARTBEAT_INTERVAL_MINUTES=30
MAX_CONVERSATION_LENGTH=100

# Storage Paths (Docker handles these via volumes)
STATE_DIR=/app/state
WORKSPACE_DIR=/app/workspace

# Logging
LOG_LEVEL=INFO

# Development Only (remove in production)
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...

# Testing (used in docker-compose.test.yml)
# MOCK_LLM_RESPONSES=false
GATEWAY_PORT=8000

# Logging
LOG_LEVEL=INFO
```

---

### Deployment Steps

#### Production Deployment (End Users)

```bash
# 1. Clone repository
git clone https://github.com/yourusername/openpaw.git
cd openpaw

# 2. Configure environment
cp .env.example .env
nano .env  # Add your API keys

# 3. Start all services (production mode)
docker-compose up -d

# 4. Check logs
docker-compose logs -f worker whatsapp-listener

# 5. Verify Temporal UI
open http://localhost:8080

# 6. Send test WhatsApp message
# Message the WhatsApp number linked via neonize

# 7. Monitor in Temporal UI
# Go to http://localhost:8080/workflows
# See your workflow: whatsapp-{phone-number}

# 8. Scale workers (if needed)
docker-compose up -d --scale worker=3

# 9. Stop services
docker-compose down

# 10. Stop and remove volumes (⚠️ deletes state!)
docker-compose down -v
```

#### Development Deployment

```bash
# 1. Start with development overrides (hot reload!)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# 2. Code changes auto-reload (no restart needed)
# Edit src/workflows/agent_workflow.py → worker restarts automatically

# 3. Run tests in separate terminal
docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pytest

# 4. Access Python debugger
docker-compose -f docker-compose.yml -f docker-compose.dev.yml \
  exec worker python -m ipdb

# 5. View logs with color
docker-compose -f docker-compose.yml -f docker-compose.dev.yml \
  logs -f --tail=100 worker
```

#### Testing Deployment (CI/CD)

```bash
# Run full test suite
docker-compose -f docker-compose.yml -f docker-compose.test.yml up \
  --abort-on-container-exit

# Exit code 0 = all tests passed
echo $?

# Clean up after tests
docker-compose -f docker-compose.yml -f docker-compose.test.yml down -v
```

---

### Efficient Iteration Workflow 🔁

**Philosophy**: Build once, iterate fast. Don't rebuild containers unless dependencies change.

#### Initial Setup (One Time)

```bash
# 1. Build all services
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build

# 2. Start services with hot reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 3. Verify everything is running
docker-compose ps
```

#### Fast Development Loop

**Workflow code changes** (most common):
```bash
# Edit src/workflows/agent_workflow.py
# → Worker auto-restarts (watchdog detects change)
# → No rebuild needed! ✅

# View logs to confirm reload
docker-compose logs -f worker --tail=20
```

**Activity code changes**:
```bash
# Edit src/activities/llm.py
# → Worker auto-restarts
# → Test by sending WhatsApp message or running tests

# Quick test: run single test file
docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pytest tests/test_llm.py -v
```

**Tool definition changes**:
```bash
# Edit tools/bash/TOOL.md
# → No restart needed (loaded fresh each workflow run)
# → Just send new message to test

# View state.md to verify tool was loaded
cat ./state/whatsapp-123456/state.md
```

**Testing**:
```bash
# Run specific test (fast!)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pytest tests/test_bash.py::test_bash_executor -v

# Run all tests in file
docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pytest tests/test_activities.py -v

# Run with coverage
docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pytest --cov=src --cov-report=term-missing

# IMPORTANT: No need to rebuild! Just re-run test container ✅
```

**Debugging**:
```bash
# View real-time logs from multiple services
docker-compose logs -f worker whatsapp-listener

# Tail specific service
docker-compose logs -f worker --tail=50

# Check state files
ls -la ./state/
cat ./state/whatsapp-*/state.md

# Inspect workspace
ls -la ./workspace/

# Shell into worker for debugging
docker-compose exec worker bash
```

**When to Rebuild** (rare):
```bash
# Only rebuild if you changed:
# - requirements.txt (new Python package)
# - Dockerfile / Dockerfile.dev
# - System dependencies

docker-compose -f docker-compose.yml -f docker-compose.dev.yml build worker
docker-compose restart worker
```

#### Typical Development Session

```bash
# Morning: Start everything (once)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Edit code → auto-reload (10-30 times/day)
vim src/workflows/agent_workflow.py
# Watch logs: docker-compose logs -f worker

# Run tests as needed (5-10 times/day)
docker-compose run --rm pytest tests/test_workflows.py -v

# View state.md files (anytime)
cat ./state/whatsapp-*/state.md

# End of day: Stop everything
docker-compose down
```

#### Token-Saving Tips

**1. Don't rebuild unless necessary**
- ❌ `docker-compose up --build` (rebuilds every time)
- ✅ `docker-compose up` (uses existing images)

**2. Use targeted test runs**
- ❌ `pytest tests/` (runs all 50+ tests)
- ✅ `pytest tests/test_llm.py::test_call_llm -v` (runs 1 test)

**3. View logs efficiently**
- ❌ `docker-compose logs worker` (entire log history)
- ✅ `docker-compose logs worker --tail=20 -f` (last 20 lines + follow)

**4. State inspection**
- ❌ `docker exec -it worker cat /app/state/...` (verbose)
- ✅ `cat ./state/whatsapp-*/state.md` (direct access via bind mount!)

**5. Restart only what changed**
- ❌ `docker-compose restart` (restarts all services)
- ✅ `docker-compose restart worker` (restarts one service)

---

#### Kubernetes Deployment

> **Note**: See `upgrade-ideas.md` Section 12 for Kubernetes deployment with multi-node support. Not needed for MVP.

#### Troubleshooting

**Issue: Worker can't connect to Temporal**
```bash
# Check if Temporal is healthy
docker-compose exec temporal tctl cluster health

# Check network connectivity
docker-compose exec worker ping temporal

# View worker logs
docker-compose logs worker
```

**Issue: State files not persisting**
```bash
# Verify volume exists
docker volume ls | grep agent-state

# Inspect volume
docker volume inspect openpaw_agent-state

# Check file permissions
docker-compose exec worker ls -la /app/state

# Manually inspect state file
docker-compose exec worker cat /app/state/whatsapp-123456/state.md
```

**Issue: Multiple workers not sharing state**
```bash
# Verify volume is shared (not bind mount)
docker-compose config | grep -A 5 "volumes:"

# Check if all workers see same files
docker-compose exec worker ls /app/state
docker-compose scale worker=2
docker-compose exec --index=2 worker ls /app/state  # Should be same!
```

**Issue: NFS mount failing (multi-host)**
```bash
# Test NFS mount manually
sudo mount -t nfs 192.168.1.100:/mnt/openpaw/state /mnt/test

# Check NFS exports on server
showmount -e 192.168.1.100

# Verify NFS client packages installed
dpkg -l | grep nfs-common
```

---

### Deployment Checklist

**Before Production:**
- [ ] `.env` file configured with real API keys
- [ ] Shared volumes configured (named volumes or NFS)
- [ ] Health checks passing
- [ ] Temporal UI accessible
- [ ] Worker logs show successful connection
- [ ] WhatsApp Listener connected via neonize (QR scanned, device linked)
- [ ] Test message sent and received
- [ ] state.md files being created
- [ ] Multiple workers tested (scale to 2, verify state sharing)
- [ ] Backup strategy for state files
- [ ] Monitoring/alerting configured (optional)

**Production Monitoring:**
- [ ] Temporal UI: http://localhost:8080
- [ ] Worker logs: `docker-compose logs -f worker`
- [ ] Listener logs: `docker-compose logs -f whatsapp-listener`
- [ ] Disk usage: `docker system df`
- [ ] Volume size: `du -sh $(docker volume inspect openpaw_agent-state --format '{{.Mountpoint}}')`

---

## Additional Considerations

### Security

1. **API Key Management**
   - Store keys in environment variables (never in code)
   - Consider using secrets management (AWS Secrets Manager, HashiCorp Vault)

2. **Bash Command Safety**
   - Whitelist allowed commands (optional)
   - Run in sandboxed environment (Docker, restricted user)
   - Implement approval workflow for dangerous commands

3. **Network Security**
   - Use HTTPS for gateway endpoints
   - Validate webhook signatures (Slack, GitHub)
   - Rate limiting on gateway

### Scalability

1. **Horizontal Scaling**
   - Run multiple worker instances
   - Temporal handles task distribution automatically
   - Scale based on queue depth

2. **Storage Scaling**
   - Partition state files by workflow ID
   - Consider cloud storage (S3) for archival

3. **Caching**
   - Cache LLM responses (optional)
   - Cache frequently accessed state.md files

### Observability

1. **Logging**
   - Structured logging (JSON format)
   - Log levels: DEBUG, INFO, WARNING, ERROR
   - Ship logs to centralized system (ELK, CloudWatch)

2. **Metrics**
   - Activity duration
   - Workflow duration
   - LLM token usage
   - Error rates

3. **Tracing**
   - Temporal provides built-in tracing
   - Integrate with OpenTelemetry for detailed traces

### Future Enhancements

1. **Multi-Modal Tools**
   - Image generation (DALL-E, Midjourney)
   - Speech-to-text (Whisper)
   - Text-to-speech

2. **Advanced Memory** (when needed)
   - Vector search: Add when state.md > 50KB or need semantic search
   - Automatic summarization of old conversations
   - Knowledge graph extraction
   - Shared knowledge base across multiple agents

3. **Collaboration**
   - Multi-agent collaboration (agents calling other agents)
   - Shared memory between agents
   - Workflow orchestration for complex tasks

4. **UI Dashboard**
   - Web UI for managing agents
   - Conversation viewer
   - Configuration editor

---

## Design Philosophy: Simplicity First

This plan follows a **"start simple, add complexity when needed"** approach:

### What We Kept Simple

1. **Memory/State Management**: Simple markdown files (state.md) instead of vector databases
   - Modern LLMs have 100K-200K token contexts - plenty for most use cases
   - LLM naturally does "semantic search" over the full state.md content
   - Easy to debug: `cat state/agent-001/state.md`
   - No embedding costs, no database setup

2. **No Premature Optimization**: Built for clarity, not hypothetical scale
   - Can add vector search later if state.md grows too large (rare)
   - Can add caching/indexing when actually needed
   - YAGNI principle: You Ain't Gonna Need It (until you do)

### When to Add Complexity Later

Add **vector search** if you hit these limits:
- state.md files > 50KB consistently
- Need to search across 1000s of documents
- Multi-agent shared knowledge base
- Semantic search is critical requirement

The architecture makes it easy to add:
```python
# Future: Add background indexing
@activity.defn
async def index_state_to_vector_db(workflow_id: str):
    # Read state.md
    # Generate embeddings
    # Store in vector DB
    pass
```

But for most personal assistant use cases: **simple state.md is fine**.

---

## Conclusion

This architecture provides a robust foundation for building a Temporal-based agentic system inspired by OpenClaw. The key advantages are:

1. **Full Observability**: Temporal UI shows every step of agent execution
2. **Fault Tolerance**: Automatic retries, failure recovery
3. **Scalability**: Horizontal scaling of workers
4. **Flexibility**: Easy to add new tools, workflows, activities
5. **State Management**: Durable workflow state + state.md for cross-run memory
6. **Simplicity**: Start with simple patterns, add complexity only when needed

The implementation plan breaks the work into manageable phases over 7-8 weeks, with clear deliverables and testing strategies at each stage. The Docker Compose setup makes deployment straightforward, and the modular architecture allows for future enhancements without overengineering upfront.

**Next Steps**: Review this plan, validate the architecture with stakeholders, and begin Phase 1 implementation.
