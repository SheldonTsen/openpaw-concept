# OpenPaw Behaviour

## Configuration

Check out `src/openpaw/config.py` for everything you can configure.

## `/btw` — Ask a Side Question While the Agent is Busy

Sometimes you remember something mid-task. Maybe the agent is running a long operation and you want to ask an unrelated question without interrupting it.

Use `/btw` for that.

```
/btw what was the name of that Python package we used for retries?
/btw how do I check disk usage on Linux?
/btw remind me what we decided about the database schema
```

The agent will answer your question and send the response back to you directly. Your original task keeps running — nothing is cancelled or paused.

### What to expect

- The response arrives separately from the main task. It may come back quickly, or take a moment depending on what the agent is already doing.
- The agent has full context of your conversation *up to the moment you sent the `/btw`*, so you can refer to things discussed earlier in the session.
- The exchange is self-contained. If the agent looks something up to answer your question (searches the web, reads a file, runs a command), that result is not fed back into the main task. If you want the main agent to act on something from a `/btw` answer, send it as a follow-up message.
- `/btw` is for questions, not new tasks. If you want to give the agent new work, just send a normal message (it will be queued and handled once the current task finishes).
