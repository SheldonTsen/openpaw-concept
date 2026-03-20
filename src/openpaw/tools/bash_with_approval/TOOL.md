---
name: bash_with_approval
description: Execute bash commands with human approval required before execution
parameters:
  type: object
  properties:
    command:
      type: string
      description: The bash command to execute (requires user approval)
    timeout:
      type: integer
      description: Optional timeout in seconds (default 30, max 300)
      default: 30
  required:
    - command
metadata:
  type: cli
  activity: execute_bash_command
  tier: essential
  priority: 2
---

# Bash Command Execution (With Approval)

Execute shell commands with human-in-the-loop approval. The user will be
asked to approve or deny each command before it runs.

Use this tool for any bash commands that may be destructive or sensitive.
The user will see the command and can reply YES or NO.

## Usage

Same as the regular bash tool, but the user must approve each command before execution.

## Notes

- Commands are shown to the user before execution
- User must reply YES to approve or NO to deny
- Approval times out after 5 minutes (command is denied)
- If running in a sub-agent context without approval support, commands execute immediately
