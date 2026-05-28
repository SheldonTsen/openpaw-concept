# Memory Architecture (Draft / Ideas)

Status: **pre-design** — ideas not yet committed to.

---

## Problem

The current approach stores only the LLM conversation history (user/assistant/tool messages) in memory, and discards older turns via compaction.

- Compaction is lossy: an LLM summarises the conversation, summaries hallucinate and drop detail.
- The agent has no way to look up what it did in a past session.
- There is no audit trail. A developer can't easily ask "what did the agent actually run on Tuesday?"

---

## Memory Hierarchy

Inspired by how CPU caching works — data floats up on demand, gets evicted when no longer needed, with a small curated set always hot:

| Layer | Analogy | What it is |
|---|---|---|
| Core memories | Registers | Always in system prompt, user-curated via `/remember` / `/forget` |
| Working memory | L1 cache | Current `conversation_history`, trimmed by compaction |
| Memory view | L2 cache | Filtered SQL view of events — high-signal story, no tool noise |
| Events table | Disk | Full append-only log, never deleted, queried on demand |

Nothing floats up automatically — you query down explicitly. `search_memory` hits the memory view, `search_events` hits the events table. Core memories are the only layer always loaded, and the user controls what goes there.

---

## Core Insight

Actions without conversation context are meaningless. The conversation history and the event log aren't two separate things — they're the same linear story:

```
message_in → tool_call → tool_result → message_out → ...
```

The fix: **persist this to a database**, never delete it, add a `session_id`. A developer can then run:

```sql
SELECT timestamp, event_type, content
FROM events
WHERE chat_id = '1234567890'
ORDER BY timestamp;
```

...and see the complete linear history of everything that happened for that chat.

### Why not use Temporal's event history?

Temporal already records every activity input and output — the Temporal UI shows exactly this. But it's the wrong layer to expose to the agent:

- History is scoped to a single workflow execution. After a timeout or `continue_as_new`, prior runs are separate.
- Temporal has configurable retention (7–30 days typically). Not designed for long-term memory.
- The agent would need to know it's running inside Temporal to query it. That coupling is wrong.

---

## Design

### Core Memories

A small table of user-curated facts that are **always injected into the system prompt** on every request. Kept tight — not a dump of history, just things the user has explicitly decided the agent should always know.

```python
@dataclass
class CoreMemory:
    memory_id: str
    chat_id: str
    content: str       # e.g. "User prefers concise responses"
    created_at: datetime
```

System prompt becomes:

```
[base instructions]

## What I always keep in mind
- You prefer concise responses
- You're working on openpaw
- You use uv for package management
```

**How entries are added:** `/remember <fact>` mid-conversation. No automatic inference.

**How entries are removed:** `/forget <number>` in response to the weekly heartbeat review (see Heartbeat section).

---

### Working Memory (unchanged)

The in-memory `conversation_history` list. Fills as the session runs, trimmed when it hits `COMPACTION_THRESHOLD`. No change to how this works — it's just the live window for the current session.

---

### Events Table (append-only, never deleted)

One table. Every event is a row. Source of truth.

```python
@dataclass
class AgentEvent:
    event_id: str          # uuid
    chat_id: str           # conversation identifier
    session_id: str        # one per workflow execution
    session_type: str      # "user" | "heartbeat"
    workflow_id: str       # temporal workflow id
    timestamp: datetime
    event_type: str        # see below
    content: str           # serialised input or output
    tool_name: str | None  # set for tool_call / tool_result
    success: bool | None
    duration_ms: int | None
```

| event_type | Written when |
|---|---|
| `message_in` | User sends a message |
| `message_out` | Agent sends a reply |
| `tool_call` | Agent dispatches a tool |
| `tool_result` | Tool returns |
| `subagent_prompt` | SubAgentWorkflow is spawned |
| `subagent_response` | SubAgentWorkflow returns |
| `heartbeat_trigger` | HeartbeatWorkflow fires a poke |

`llm_call` omitted — high volume, story is already told by surrounding events.

#### Indexes

```sql
CREATE INDEX idx_events_chat_time    ON events (chat_id, timestamp);
CREATE INDEX idx_events_chat_session ON events (chat_id, session_id);
```

#### Memory View

A SQL view over the events table — no separate storage.

The events table is the fully-sampled signal. The memory view is decimation: downsample by keeping only the semantic conversation and dropping everything else. Tool calls, subagent internals, heartbeats — all high-frequency noise. The user's question and the agent's final answer are the low-frequency signal worth keeping.

`delegate_task` results don't need special-casing — they're already synthesised into the agent's `message_out`. The mechanism is noise; the answer is the signal.

```sql
CREATE VIEW memory AS
SELECT timestamp, chat_id, event_type, content
FROM events
WHERE session_type = 'user'
  AND event_type IN ('message_in', 'message_out');
```

`session_id` and `session_type` are intentionally excluded from this view — they're irrelevant at this resolution. Both columns stay on the events table for full-fidelity developer queries and future analytics (e.g. "show all heartbeat sessions", "how many user sessions this week").

Raw tool calls and subagent detail are still accessible via `search_events` when precision is needed.

---

## Session Boundaries

A session = one workflow execution.

- **Workflow starts** → new `session_id`, type `"user"` or `"heartbeat"`
- **Workflow timeout** → session ends naturally
- **Heartbeat poke** → starts or signals AgentWorkflow. If a new execution starts, that's a new session tagged `"heartbeat"`
- **`/btw` or `delegate_task`** → events within the parent session (`subagent_prompt` / `subagent_response`), not a new session

---

## Compaction

When `conversation_history` hits `COMPACTION_THRESHOLD`:

1. Query the `memory` view for this `session_id` from the DB.
2. LLM summarises from those rows.
3. Replace working memory with `[SUMMARY: ...]` + last N messages.
4. Events table untouched.

---

## Heartbeat — Varied Behavior

The existing `HeartbeatWorkflow` already has a `_poke_count` counter. Use it to vary what happens at each tick rather than always sending the same message:

```python
if poke_count % MEMORY_REVIEW_EVERY == 0:
    message = memory_review_message(chat_id)  # weekly
elif poke_count % REMINDER_EVERY == 0:
    message = REMINDER_MESSAGE                # daily
else:
    message = HEARTBEAT_MESSAGE               # regular check-in
```

Intervals expressed as poke counts (each poke = `HEARTBEAT_INTERVAL_MINUTES`):

```python
# example: 15-min heartbeat
HEARTBEAT_INTERVAL_MINUTES = 15
REMINDER_EVERY   = 96   # 96 × 15min = 24h
MEMORY_REVIEW_EVERY = 672  # 672 × 15min = 7 days
```

### Memory review message

Once a week the heartbeat sends the current core memory list and waits passively:

> *"Here's what I always keep in mind:*
> *1. You prefer concise responses*
> *2. You're working on openpaw*
> *3. You use uv for package management*
>
> *Reply `/forget <number>` to remove anything, or ignore to keep as-is."*

One message. No yes/no questions, no candidates to evaluate. User ignores it if happy, removes with a single command if not. The agent doesn't follow up.

---

## Agent Tools

**`search_memory`** — queries the `memory` view (user-initiated sessions only, `message_in` + `message_out`):
```python
search_memory(query="database migration", days_back=14)
# → what the user asked and what the agent replied, filtered by query
```

**`search_events`** — queries the raw events table (full detail):
```python
search_events(session_id="...", event_types=["tool_call", "tool_result"])
# → every tool call and result for that session
```

The agent starts coarse (`search_memory`) and drills down (`search_events`) if it needs precision.

---

## Storage Backend

`aiosqlite` + raw SQL. One `events` table, one `core_memories` table. No ORM.

If we ever need Postgres, the schema is simple enough that swapping `aiosqlite` for `asyncpg` and adjusting ~5 queries is the full migration cost.

**DB lives at:** `data/memory/events.db` — same Docker volume as state files, accessible to all workers. SQLite WAL mode handles concurrent writes from multiple workers fine for this workload.

---

## Open Questions

1. **agentfs spike** — does adding `chat_id` / `session_id` feel natural or like fighting the library?

2. **Heartbeat noise** — if heartbeat interval is short, `memory` view accumulates many heartbeat rows. May want to only log heartbeats that produced a meaningful agent response, not every poke.

3. **Core memory injection** — always in system prompt (current proposal) vs. only injected when non-empty. Probably always, even if empty, so the agent knows the mechanism exists.
