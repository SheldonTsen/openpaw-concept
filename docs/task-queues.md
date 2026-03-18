# Task Queues & Activity Routing

## Overview

The system runs two Temporal workers on two separate task queues. Both poll the same Temporal namespace (`openpaw`), but each registers different activities.

## Queues

| Queue | Container | Config constant | Polls for |
|---|---|---|---|
| `agent-tasks` | `worker` | `TASK_QUEUE` | Workflows + all activities except WhatsApp send |
| `whatsapp-tasks` | `whatsapp-listener` | `WHATSAPP_TASK_QUEUE` | `send_whatsapp_message` only |

## Why Two Queues?

`send_whatsapp_message` calls `neonize_client.send_message()`, which is a synchronous Go FFI call. The neonize client (and its WhatsApp session) lives exclusively in the listener container. The worker container has no access to it.

By putting `send_whatsapp_message` on a separate queue, the workflow can dispatch it to whichever worker has the neonize client, while all other activities run on the main worker.

## How Routing Works

Activities dispatched **without** an explicit `task_queue` run on the workflow's default queue (`agent-tasks`). The workflow explicitly routes `send_whatsapp_message` to the WhatsApp queue:

```python
await workflow.execute_activity(
    "send_whatsapp_message",
    arg=SendMessageInput(phone_number=chat_id, text=response_text),
    task_queue=WHATSAPP_TASK_QUEUE,  # <-- explicit routing
    ...
)
```

All other `execute_activity` calls omit `task_queue`, so Temporal routes them to the workflow's own queue (`agent-tasks`).

## Diagram

```
WhatsApp user
    |
    v
[whatsapp-listener container]
    |- main thread: neonize client (Go FFI, blocking)
    |- daemon thread: Temporal worker polling `whatsapp-tasks`
    |    \_ send_whatsapp_message activity
    |
    | start_workflow / signal
    v
[Temporal server]
    |
    v
[worker container]
    |- Temporal worker polling `agent-tasks`
    |    \_ AgentWorkflow
    |    \_ call_llm, save_state, load_state, bash, file I/O, etc.
    |
    | execute_activity(task_queue="whatsapp-tasks")
    v
[whatsapp-listener container]  <-- routed back for send
```
