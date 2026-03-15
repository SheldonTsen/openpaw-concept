# Terminal UI Ideas

## Current Problem

The CLI uses `input("> ")` for user input and `print("\nAgent: ...")` for output. These share the same stdout stream, so when an agent response arrives it disrupts the prompt line. The `> ` disappears after the agent prints, and if the user is mid-typing the output lands in the middle of their text.

This is inherent to mixing async output with blocking `input()` on a single stream.

## Option 1: Curses-based split pane

Use Python's built-in `curses` library. Two regions:

- **Top region**: scrollable message log (agent responses, system messages)
- **Bottom region**: fixed input line with `> ` prompt, always visible

Pros:
- No external dependencies
- Full control over rendering
- Input line never gets clobbered by output

Cons:
- `curses` API is verbose and low-level
- No Windows support (though not a priority)
- Have to handle terminal resize, scrolling, line wrapping manually

## Option 2: prompt_toolkit

`prompt_toolkit` is a mature library for building terminal UIs in Python (used by IPython, pgcli, etc).

- Supports async natively (`prompt_toolkit.patch_stdout` redirects prints above the prompt)
- The input prompt stays pinned at the bottom automatically
- Handles multi-line input, history, auto-complete for free

Minimal approach: just use `patch_stdout()` context manager. All `print()` calls (including from the activity) render above the prompt. The `> ` input line stays at the bottom untouched.

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

session = PromptSession()
with patch_stdout():
    while True:
        text = await session.prompt_async("> ")
        # send signal...
```

Pros:
- Solves the exact problem with ~5 lines of code
- Battle-tested (IPython uses it)
- Async-native, fits our event loop
- Input history (arrow keys) for free

Cons:
- New dependency
- Might be overkill if we want something minimal

## Option 3: Rich Live display

Use `rich` library with a `Live` display for the message log and a separate input mechanism.

Pros:
- Pretty formatted output (markdown, syntax highlighting)
- Could render agent responses with nice formatting

Cons:
- `rich` doesn't natively handle input — would still need `prompt_toolkit` or similar for the input line
- Heavier dependency for what we need

## Option 4: Simple reprinting

After the agent prints, reprint the `> ` prompt (and any partial input the user has typed). No TUI library needed.

This is fragile — we'd need to track what the user has typed so far (which `input()` doesn't expose) and deal with terminal escape codes. Not worth it.

## Recommendation

**Option 2 (prompt_toolkit)** solves the problem cleanly with minimal code. `patch_stdout()` is purpose-built for exactly this scenario: async output that shouldn't disturb the input prompt. No need to build a full curses TUI.

If we later want richer formatting (markdown rendering, colors), we can layer `rich` on top for the output while keeping `prompt_toolkit` for input.
