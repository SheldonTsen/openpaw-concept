---
name: write_file
description: Write content to a file in the workspace
parameters:
  type: object
  properties:
    path:
      type: string
      description: File path relative to workspace root or absolute path
    content:
      type: string
      description: Content to write to the file
    mode:
      type: string
      description: Write mode - 'overwrite' (default) or 'append'
      default: overwrite
      enum:
        - overwrite
        - append
  required:
    - path
    - content
metadata:
  type: activity
  activity: write_file_activity
  tier: experimental
  priority: 3
  retry_policy:
    maximum_attempts: 2
    backoff_coefficient: 1.5
---

# Write File

Write or append content to a file in the workspace.

## Usage

Use this tool to create new files, update existing files, save outputs, or append to logs.

## Examples

```python
# Create a new Python file
write_file(
    path="app/utils.py",
    content="def hello():\n    print('Hello, World!')\n"
)

# Update configuration file
write_file(
    path="config.yaml",
    content="api_key: sk-123\nendpoint: https://api.example.com\n"
)

# Append to log file
write_file(
    path="logs/activity.log",
    content="[2026-02-28] Task completed successfully\n",
    mode="append"
)

# Create data file
write_file(
    path="data/results.csv",
    content="name,score\nAlice,95\nBob,87\n"
)
```

## Modes

- **overwrite** (default): Replaces entire file contents
- **append**: Adds content to end of existing file

## Notes

- Parent directories are created automatically if they don't exist
- Overwrites existing files by default (use `mode=append` to preserve)
- Use Unix-style line endings (`\n`)
- Paths can be relative to workspace root or absolute
- Large writes (>10MB) may fail or be slow

## Common Use Cases

- Creating source code files
- Saving analysis results
- Generating reports or documentation
- Writing configuration files
- Logging progress or errors
- Saving data exports

## Safety

- **No confirmation**: Files are overwritten without warning
- **Backup first**: Read file before overwriting if preservation needed
- **Check paths**: Ensure path is correct to avoid data loss
