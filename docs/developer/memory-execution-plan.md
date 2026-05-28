# Memory — Execution Plan

Phases build on each other. Complete and verify each before starting the next.

---

## Phase 1 — Event Collection (foundation)

**Goal:** Every action is persisted. A developer can query `events` and see the full linear history for any chat.

### 1.1 DB setup

New file `src/openpaw/memory/db.py`:

```python
# initialise DB, create tables + indexes + view on first connect

CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    chat_id      TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    session_type TEXT NOT NULL,   -- "user" | "heartbeat"
    workflow_id  TEXT NOT NULL,
    timestamp    TEXT NOT NULL,   -- ISO8601
    event_type   TEXT NOT NULL,   -- "message_in" | "message_out" | "tool_call" | ...
    content      TEXT NOT NULL,
    tool_name    TEXT,
    success      INTEGER,         -- 1 | 0 | NULL
    duration_ms  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_events_chat_time
    ON events (chat_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_events_chat_session
    ON events (chat_id, session_id);

CREATE VIEW IF NOT EXISTS memory AS
SELECT timestamp, chat_id, event_type, content
FROM events
WHERE session_type = 'user'
  AND event_type IN ('message_in', 'message_out');

CREATE TABLE IF NOT EXISTS core_memories (
    memory_id  TEXT PRIMARY KEY,
    chat_id    TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 1.2 New activity — `log_event`

New file `src/openpaw/activities/memory.py`:

```python
@activity.defn(name="log_event")
async def log_event(input: LogEventInput) -> None:
    # insert row into events table
    # fire and forget — no return value needed
```

`LogEventInput` mirrors the `AgentEvent` dataclass from the design doc.

### 1.3 Wire into workflows

`AgentWorkflow`:
- `new_message` signal → log `message_in` (session_type derived from whether it matches `HEARTBEAT_MESSAGE`)
- `_send_status` (final reply only, not the "🔧 Using..." intermediates) → log `message_out`
- `_dispatch` before call → log `tool_call`
- `_dispatch` after call → log `tool_result` (include success, duration_ms)

`SubAgentWorkflow` (for `/btw`):
- on start → log `subagent_prompt` under parent session_id
- on completion → log `subagent_response` under parent session_id

`HeartbeatWorkflow`:
- before `poke_agent` → log `heartbeat_trigger`

`session_id` = `workflow.info().workflow_id` — already available inside workflows.

### 1.4 Verify

```bash
# after a short conversation
sqlite3 data/memory/events.db \
  "SELECT timestamp, event_type, tool_name, substr(content,1,80) FROM events ORDER BY timestamp;"
```

Should see the full interleaved story in time order.

---

## Phase 2 — Memory View + Agent Search Tools

**Goal:** Agent can look up what it did in past sessions.

### 2.1 New activities

In `src/openpaw/activities/memory.py`:

```python
@activity.defn(name="search_memory")
async def search_memory(input: SearchMemoryInput) -> list[dict]:
    # query the `memory` view
    # filter by chat_id, days_back, optional keyword (LIKE on content)
    # return list of {timestamp, event_type, content}

@activity.defn(name="search_events")
async def search_events(input: SearchEventsInput) -> list[dict]:
    # query raw events table
    # filter by chat_id, session_id, event_types list
    # return full rows
```

### 2.2 New tool handlers

`src/openpaw/tool_handlers/search_memory.py`:

```python
async def handle(args: dict, **kwargs) -> str:
    # call search_memory activity via workflow.execute_activity
    # format results as readable text for LLM
```

`src/openpaw/tool_handlers/search_events.py`:

```python
async def handle(args: dict, **kwargs) -> str:
    # call search_events activity via workflow.execute_activity
    # format results as readable text for LLM
```

### 2.3 New tool definitions

Add `tools/search_memory/` and `tools/search_events/` tool definition files (matching the existing tool loader pattern).

### 2.4 Verify

Ask the agent "what did I ask you last session?" and confirm it uses `search_memory` to find the answer.

---

## Phase 3 — Compaction Rework

**Goal:** Compaction summarises from the persisted event record rather than from `conversation_history` itself.

### 3.1 Change `compact_history` activity

Currently reads from `conversation_history` passed in as input. Change to:

```python
# instead of summarising conversation_history directly:
# 1. fetch memory view rows for this session_id from DB
# 2. summarise those rows
# 3. return summary — caller replaces working memory as before
```

`CompactHistoryInput` gains `session_id` field. The `conversation_history` field can stay for fallback if no DB rows found yet.

### 3.2 Verify

Trigger compaction (set `COMPACTION_THRESHOLD` low temporarily). Confirm summary is generated from DB rows and working memory is correctly replaced.

---

## Phase 4 — Core Memories

**Goal:** User can `/remember` facts mid-conversation. Facts always appear in system prompt.

### 4.1 New activities

```python
@activity.defn(name="add_core_memory")
async def add_core_memory(input: AddCoreMemoryInput) -> None:
    # insert into core_memories table

@activity.defn(name="get_core_memories")
async def get_core_memories(input: GetCoreMemoriesInput) -> list[CoreMemory]:
    # select all from core_memories where chat_id = ?

@activity.defn(name="delete_core_memory")
async def delete_core_memory(input: DeleteCoreMemoryInput) -> None:
    # delete from core_memories where memory_id = ?
```

### 4.2 Handle `/remember` and `/forget` signals

In `AgentWorkflow.new_message`:

```python
if text.lower().startswith("/remember "):
    fact = text[10:].strip()
    # execute add_core_memory activity
    await self._send_status("Got it, I'll always keep that in mind.")
    return

if text.lower().startswith("/forget "):
    # parse number, look up memory_id by position, delete
    # execute delete_core_memory activity
    await self._send_status("Removed.")
    return
```

### 4.3 Inject into system prompt

In `AgentWorkflow._thinking_loop`, load core memories once per session (cache on `self`) and prepend to system content:

```python
# in run(), after loading state:
self._core_memories = await workflow.execute_activity(
    get_core_memories, ...
)

# in _thinking_loop, building system_content:
core_block = ""
if self._core_memories:
    items = "\n".join(f"- {m.content}" for m in self._core_memories)
    core_block = f"\n\n## What I always keep in mind\n{items}"

system_content = f"Current time: {now}\n\n{SYSTEM_PROMPT}{core_block}\n\n## Tool Documentation\n\n{tool_docs}"
```

### 4.4 Verify

`/remember I prefer short responses` → confirm it appears in system prompt on next turn. `/forget 1` → confirm it's removed.

---

## Phase 5 — Varied Heartbeat

**Goal:** Heartbeat does different things at different intervals (check-in / daily reminder / weekly memory review).

### 5.1 Config

```python
# config.py
HEARTBEAT_INTERVAL_MINUTES = int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "15"))
REMINDER_EVERY   = int(os.getenv("REMINDER_EVERY", "96"))    # ~daily
MEMORY_REVIEW_EVERY = int(os.getenv("MEMORY_REVIEW_EVERY", "672"))  # ~weekly
REMINDER_MESSAGE = os.getenv("REMINDER_MESSAGE", "")
```

### 5.2 HeartbeatWorkflow poke logic

```python
# in HeartbeatWorkflow, before calling poke_agent:
if self._poke_count % MEMORY_REVIEW_EVERY == 0 and self._poke_count > 0:
    message = await self._build_memory_review_message(input.chat_id)
elif REMINDER_MESSAGE and self._poke_count % REMINDER_EVERY == 0 and self._poke_count > 0:
    message = REMINDER_MESSAGE
else:
    message = HEARTBEAT_MESSAGE
```

`_build_memory_review_message` calls `get_core_memories` and formats:

```
Here's what I always keep in mind:
1. You prefer concise responses
2. You're working on openpaw

Reply /forget <number> to remove anything, or ignore to keep as-is.
```

If core memories are empty, skip the memory review entirely that tick.

### 5.3 Verify

Set `MEMORY_REVIEW_EVERY=2` temporarily, trigger two heartbeat pokes, confirm the memory review message is sent on the second.

---

## Order Summary

| Phase | Delivers |
|---|---|
| 1 — Event collection | Full audit trail, developer visibility |
| 2 — Search tools | Agent can recall past sessions |
| 3 — Compaction rework | Compaction sources from DB, not self |
| 4 — Core memories | `/remember` / `/forget`, always-on context |
| 5 — Varied heartbeat | Weekly memory review, daily reminders |

Phases 1–2 are the foundation and the biggest user-visible improvement. Phases 3–5 can be deferred.
