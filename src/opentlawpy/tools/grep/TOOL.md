---
name: grep
description: Search for patterns in files using grep
parameters:
  type: object
  properties:
    pattern:
      type: string
      description: Search pattern (regex supported)
    path:
      type: string
      description: File or directory path to search (default current directory)
      default: .
    case_sensitive:
      type: boolean
      description: Case-sensitive search (default false)
      default: false
    recursive:
      type: boolean
      description: Search recursively in directories (default true)
      default: true
  required:
    - pattern
metadata:
  type: cli
  command_template: "grep {case_flag} {recursive_flag} '{pattern}' {path}"
  tier: common
  priority: 8
  retry_policy:
    maximum_attempts: 2
    backoff_coefficient: 1.5
---

# Grep - Pattern Search

Search for text patterns in files using grep with support for regular expressions.

## Usage

Use this tool to find specific text, patterns, or code snippets across files in your workspace.

## Examples

```bash
# Search for a function name
grep(pattern="def process_data", path=".")

# Case-sensitive search
grep(pattern="TODO", path="src/", case_sensitive=True)

# Search in specific file
grep(pattern="import requests", path="app.py", recursive=False)

# Search for error messages
grep(pattern="Error:|ERROR|FATAL", path="logs/")

# Find environment variables
grep(pattern="os.getenv", path=".", recursive=True)

# Search for IP addresses (regex)
grep(pattern="[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", path="config/")
```

## Pattern Types

**Literal Text**:
- `"hello world"` - Exact phrase
- `"TODO"` - Simple string

**Regular Expressions**:
- `"^import"` - Lines starting with "import"
- `"error$"` - Lines ending with "error"
- `"\bclass\b"` - Word "class" with boundaries
- `"[0-9]+"` - One or more digits
- `"(foo|bar)"` - Either "foo" or "bar"

## Result Format

Returns matching lines with:
- **File path**: Where match was found
- **Line number**: Line number in file
- **Matched line**: The line containing the pattern

## Common Use Cases

- Finding TODO comments in code
- Searching for function/class definitions
- Locating error messages in logs
- Finding configuration values
- Searching for specific imports
- Identifying hardcoded values
- Code review and auditing
- Finding deprecated API usage

## Notes

- Default is case-insensitive search
- Searches recursively by default
- Binary files are automatically skipped
- Large directories may take time
- Use specific paths to narrow search
- Regex patterns must be valid grep regex
- Special characters may need escaping

## Performance Tips

- **Narrow the path**: Search specific directories
- **Use literal strings**: Faster than complex regex
- **Exclude large files**: Use `.gitignore` patterns
- **Limit recursion**: Set `recursive=False` for single file
