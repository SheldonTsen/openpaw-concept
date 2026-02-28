---
name: python
description: Execute Python code in an isolated environment
parameters:
  type: object
  properties:
    code:
      type: string
      description: Python code to execute
    timeout:
      type: integer
      description: Timeout in seconds (default 60, max 300)
      default: 60
  required:
    - code
metadata:
  type: cli
  command_template: "python3 -c {code}"
  tier: essential
  priority: 4
  retry_policy:
    maximum_attempts: 2
    backoff_coefficient: 1.5
---

# Python Code Execution

Execute Python code in an isolated environment with common libraries pre-installed.

## Usage

Use this tool to run Python scripts, perform calculations, data analysis, text processing, or any computational task.

## Examples

```python
# Simple calculation
python(code="print(42 * 1.5)")

# Data processing
python(code="""
import json
data = {'name': 'Alice', 'age': 30}
print(json.dumps(data, indent=2))
""")

# File analysis
python(code="""
import os
files = [f for f in os.listdir('.') if f.endswith('.py')]
print(f'Found {len(files)} Python files')
""")

# Web request
python(code="""
import requests
response = requests.get('https://api.github.com/repos/python/cpython')
print(response.json()['stargazers_count'])
""")
```

## Pre-installed Libraries

**Standard Library**: All Python 3.11+ standard modules

**Common Libraries**:
- `requests` - HTTP requests
- `pandas` - Data analysis
- `numpy` - Numerical computing
- `matplotlib` - Plotting
- `beautifulsoup4` - HTML parsing
- `pyyaml` - YAML parsing
- `httpx` - Async HTTP client

## Notes

- Code runs in Python 3.11+ environment
- Use triple quotes for multi-line code
- Output is captured from stdout/stderr
- Timeout defaults to 60 seconds, max 300 seconds
- Install additional packages with `pip install` via bash tool first
- Global variables persist within the same workflow execution

## Common Use Cases

- Mathematical calculations
- Data transformation and analysis
- JSON/YAML parsing
- Web scraping
- Text processing and regex
- File format conversions
- API testing
- Quick prototyping

## Error Handling

- Syntax errors return immediately with error message
- Runtime exceptions include traceback
- Timeouts cancel execution and return timeout error
- Import errors suggest using bash tool to install package
