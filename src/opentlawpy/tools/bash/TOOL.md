---
name: bash
description: Execute bash commands in a sandboxed container environment
parameters:
  type: object
  properties:
    command:
      type: string
      description: The bash command to execute
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
  priority: 1
  retry_policy:
    maximum_attempts: 3
    backoff_coefficient: 2.0
---

# Bash Command Execution

Execute shell commands in a sandboxed container environment with persistent working directory.

## Usage

Use this tool to run bash commands, install packages, manage files, run scripts, and perform system operations.

## Examples

```bash
# List files in current directory
ls -la

# Install a Python package
pip install requests

# Run a Python script
python analyze.py --input data.csv

# Search for files
find . -name "*.py" -type f

# Check system info
uname -a
```

## Capabilities

- **Package Management**: Install packages with pip, npm, apt-get, etc.
- **File Operations**: Create, move, copy, delete files and directories
- **Script Execution**: Run Python, Node.js, or other scripts
- **System Commands**: Check processes, disk usage, environment variables

## Notes

- Commands run in an isolated container environment
- Working directory persists between calls within the same workflow
- Environment variables available: `HOME`, `USER`, `PATH`
- Timeout defaults to 30 seconds, maximum 300 seconds
- Use `&&` to chain multiple commands: `mkdir data && cd data && wget url`
- Commands are retried up to 3 times on transient failures

## Security

- Commands run with limited permissions
- No access to host system files outside container
- Network access may be restricted based on configuration
