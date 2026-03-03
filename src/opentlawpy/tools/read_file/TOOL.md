---
name: read_file
description: Read contents of a file from the workspace
parameters:
  type: object
  properties:
    path:
      type: string
      description: File path relative to workspace root or absolute path
    encoding:
      type: string
      description: File encoding (default utf-8)
      default: utf-8
  required:
    - path
metadata:
  type: activity
  activity: read_file_activity
  tier: essential
  priority: 2
  retry_policy:
    maximum_attempts: 2
    backoff_coefficient: 1.5
---

# Read File

Read the contents of a file from the workspace or container filesystem.

## Usage

Use this tool to read configuration files, source code, data files, logs, or any text-based file contents.

## Examples

```python
# Read a Python source file
read_file(path="app/main.py")

# Read a configuration file
read_file(path="config.yaml")

# Read with specific encoding
read_file(path="data.csv", encoding="utf-8")

# Read from absolute path
read_file(path="/tmp/output.txt")
```

## Supported File Types

- **Text Files**: .txt, .md, .log
- **Source Code**: .py, .js, .ts, .java, .go, .rs, etc.
- **Configuration**: .yaml, .json, .toml, .ini, .env
- **Data Files**: .csv, .tsv, .xml
- **Documentation**: .md, .rst, .tex

## Notes

- Paths can be relative to workspace root or absolute
- Default encoding is UTF-8
- Binary files will return garbled text (use appropriate encoding)
- Large files (>1MB) may be truncated
- File must exist and be readable, otherwise returns error

## Common Use Cases

- Reading source code for analysis
- Loading configuration files
- Checking log files for errors
- Reading data files for processing
- Inspecting file contents before modification
