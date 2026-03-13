# Heartbeat Workflow

## Overview

The HeartbeatWorkflow is a permanent per-chat workflow that periodically pokes the AgentWorkflow. If the agent timed out (idle timeout), the heartbeat starts a new one which loads persisted state. The heartbeat message is processed as a normal message — the LLM responds via WhatsApp.

## Architecture

```
AgentWorkflow (per chat, finite lifetime)
    └── starts HeartbeatWorkflow as abandoned child

HeartbeatWorkflow (per chat, permanent)
    loop:
        sleep HEARTBEAT_INTERVAL_MINUTES
        call poke_agent activity
            → atomic start-or-signal AgentWorkflow
```

- AgentWorkflow starts HeartbeatWorkflow on first run (`ParentClosePolicy.ABANDON`)
- HeartbeatWorkflow survives when the agent times out
- poke_agent uses `id_conflict_policy=USE_EXISTING` — if the agent is running, it just signals it; if not, it starts a new one
- HeartbeatWorkflow calls `continue_as_new` every 100 pokes to bound its own event history

## Interval vs Timeout Relationship

The relationship between `HEARTBEAT_INTERVAL_MINUTES` and `WORKFLOW_TIMEOUT_MINUTES` determines system behaviour:

### Heartbeat interval > workflow timeout (e.g. 30 min heartbeat, 15 min timeout)

- Agent idles → times out → workflow completes with bounded history
- Heartbeat pokes later → starts a fresh agent (loads persisted state)
- Temporal UI shows short-lived, completed workflows — clean and easy to browse
- Each agent execution has a small, bounded event history

### Heartbeat interval < workflow timeout (e.g. 1 min heartbeat, 15 min timeout)

- Agent never times out — heartbeat keeps resetting the idle timer
- Single long-running agent workflow per chat
- Event history grows within that execution (compaction still applies to conversation history)
- Temporal UI shows one perpetually-running workflow per chat

### Recommendation

Use `HEARTBEAT_INTERVAL_MINUTES > WORKFLOW_TIMEOUT_MINUTES` for cleaner Temporal UI and bounded event histories. The default is 30 min heartbeat with 15 min workflow timeout.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `HEARTBEAT_INTERVAL_MINUTES` | 30 | Minutes between heartbeat pokes |
| `WORKFLOW_TIMEOUT_MINUTES` | 15 | Agent workflow idle timeout |
| `HEARTBEAT_MESSAGE` | (see config.py) | Message text sent to the agent on each poke |

## Stop Signal

Send a `stop` signal to `heartbeat-{chat_id}` to permanently stop the heartbeat for a chat. The HeartbeatWorkflow exits cleanly on the next loop iteration.

## Files

- `src/opentlawpy/workflows/heartbeat_workflow.py` — HeartbeatWorkflow definition
- `src/opentlawpy/activities/heartbeat.py` — poke_agent activity (factory pattern)
- `src/opentlawpy/models/heartbeat.py` — PokeAgentInput/Output dataclasses
- `src/opentlawpy/config.py` — HEARTBEAT_INTERVAL_MINUTES, HEARTBEAT_MESSAGE
