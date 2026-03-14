---
name: delegate_task
description: Delegate a self-contained task to a sub-agent that runs independently and returns results
parameters:
  type: object
  properties:
    task:
      type: string
      description: Clear, self-contained description of the task for the sub-agent
  required:
    - task
metadata:
  type: workflow
  tier: essential
  priority: 5
---

# Delegate Task to Sub-Agent

Delegate a self-contained task to an independent sub-agent. The sub-agent runs as a separate workflow with its own thinking loop and tool access.

## When to Use

- **Complex sub-tasks**: When a task is self-contained and would pollute the main conversation with intermediate tool results
- **Parallel work**: Multiple independent sub-tasks can be delegated simultaneously
- **Context isolation**: Keep the orchestrator's context clean by offloading detailed work

## When NOT to Use

- **Simple tool calls**: If a single bash command or file read suffices, call the tool directly
- **Conversational tasks**: Sub-agents cannot ask follow-up questions
- **Tasks requiring main context**: Sub-agents don't have access to the orchestrator's conversation history

## Task Description Tips

Write the task description as if briefing a colleague:
- Be specific about what you want done
- Include any relevant file paths, commands, or constraints
- Specify the desired output format

## Examples

```
Delegate: "Read all Python files in /app/src and list any functions that don't have docstrings"
Delegate: "Install the requests library, then write a script that fetches example.com and saves the HTML to output.html"
Delegate: "Search the codebase for all TODO comments and summarize them by category"
```

## Limitations

- Sub-agents cannot delegate further (no recursion)
- Sub-agents have a shorter iteration limit and timeout
- Sub-agents don't have access to the parent's conversation history
- Results are returned as a summary string
