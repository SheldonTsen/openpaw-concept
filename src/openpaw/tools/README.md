# Tools Directory

This directory contains tool definitions for the openpaw agent system. Each tool is defined as a markdown file with YAML frontmatter, inspired by OpenClaw's skill system.

## Structure

```
tools/
├── README.md                    # This file
├── bash/
│   └── TOOL.md                 # Bash command execution
├── read_file/
│   └── TOOL.md                 # Read file contents
├── write_file/
│   └── TOOL.md                 # Write to files
├── python/
│   └── TOOL.md                 # Execute Python code
├── web_search/
│   └── TOOL.md                 # Search the web
├── git/
│   └── TOOL.md                 # Git operations
├── grep/
│   └── TOOL.md                 # Pattern search in files
└── calculator/
    └── TOOL.md                 # Mathematical calculations
```

## Tool Tiers

### Essential Tier (Priority 1-5)
Always included in MVP. Core tools for basic operations.

- **bash** (priority 1) - Execute shell commands
- **read_file** (priority 2) - Read file contents
- **write_file** (priority 3) - Write to files
- **python** (priority 4) - Execute Python code

### Common Tier (Priority 6-15)
Included in MVP. Commonly used tools for everyday tasks.

- **web_search** (priority 6) - Search DuckDuckGo
- **git** (priority 7) - Version control operations
- **grep** (priority 8) - Search patterns in files
- **calculator** (priority 9) - Mathematical calculations

## TOOL.md Format

Each tool is defined in a `TOOL.md` file with the following structure:

```markdown
---
name: tool_name
description: Brief description
parameters:
  type: object
  properties:
    param_name:
      type: string
      description: Parameter description
  required:
    - param_name
metadata:
  type: cli | activity
  activity: activity_name        # For activity-backed tools
  command_template: "cmd {arg}"  # For CLI-backed tools
  tier: essential | common | specialized | experimental
  priority: 1-999
  retry_policy:
    maximum_attempts: 3
    backoff_coefficient: 2.0
---

# Tool Name

Detailed description of what the tool does.

## Usage

How to use this tool effectively.

## Examples

```bash
# Example 1
tool_name(param="value")
```

## Notes

Important notes about the tool.
```

## Tool Types

### CLI-Backed Tools
Tools that wrap existing command-line utilities. No Python code needed!

**Characteristics**:
- `type: cli`
- `command_template` with parameter placeholders
- Generic `execute_bash_command` activity handles execution
- Easy to add - just create TOOL.md

**Examples**: web_search, git, grep, calculator

### Activity-Backed Tools
Tools that require custom Python implementation.

**Characteristics**:
- `type: activity`
- `activity` name references Python function
- Custom logic (API calls, complex processing)
- Requires Python activity implementation

**Examples**: read_file, write_file

## Adding a New Tool

### Option 1: CLI-Backed (No Python Code)

1. Create directory: `tools/my_tool/`
2. Create `TOOL.md`:

```markdown
---
name: my_tool
description: Does something useful
parameters:
  type: object
  properties:
    input:
      type: string
metadata:
  type: cli
  command_template: "mytool --option {input}"
  tier: common
  priority: 10
---

# My Tool

Description and examples...
```

3. Restart worker - tool is automatically available!

### Option 2: Activity-Backed (Custom Logic)

1. Create directory: `tools/my_tool/`
2. Create `TOOL.md`:

```markdown
---
name: my_tool
description: Does something complex
metadata:
  type: activity
  activity: my_tool_activity
  tier: common
  priority: 10
---
```

3. Implement activity in `openclaw/activities.py`:

```python
@activity.defn
async def my_tool_activity(input: dict) -> str:
    # Your custom logic here
    return result
```

4. Restart worker - tool is available!

## Loading Configuration

Tools are loaded based on tier configuration:

```python
# Load only essential + common (MVP)
tools = load_tools_from_directory(
    TOOLS_DIR,
    include_tiers=["essential", "common"],
    max_tools=30,
    max_chars=15_000
)
```

## Limits (MVP)

- **Max tools in prompt**: 30
- **Max total chars**: 15,000 (~3,750 tokens)
- **Included tiers**: essential + common
- **Expected total**: ~8 tools, ~8,000 chars

## Benefits

✅ **Easy to add** - Just drop TOOL.md, no Python for CLI tools
✅ **Rich context** - Full markdown documentation for LLM
✅ **No bloat** - Tier-based filtering
✅ **Human-readable** - Markdown is easy to read and edit
✅ **Version control** - Git-friendly markdown format
✅ **Self-documenting** - Examples and notes in tool definition

## Future Enhancements

See `upgrade-ideas.md` for:
- Semantic tool selection (embedding-based)
- Dynamic tool loading
- User-specific tool permissions
- Tool usage analytics
