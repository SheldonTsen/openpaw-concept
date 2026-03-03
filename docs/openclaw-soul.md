# How OpenClaw Handles Agent Personality ("Soul")

Reference notes from exploring the OpenClaw codebase. To revisit when we implement self-evolving personality (likely Phase 3+).

## Core Concept

Agent personality lives in **files, not config**. Plain markdown that the agent reads, embodies, and can edit itself.

## Bootstrap Files (loaded each session)

| File | Purpose | Agent-writable? |
|---|---|---|
| `SOUL.md` | Personality, values, tone, boundaries | Yes |
| `IDENTITY.md` | Name, avatar, vibe metadata | Yes |
| `AGENTS.md` | Workspace rules & safety practices | Yes |
| `USER.md` | Info about the owner | Yes |
| `MEMORY.md` | Curated long-term memories | Yes |
| `memory/YYYY-MM-DD.md` | Daily session logs | Yes |
| `HEARTBEAT.md` | Periodic check-in checklist | Yes |
| `TOOLS.md` | Local tool notes | Yes |

All stored in workspace root (`~/.openclaw/workspace/`).

## System Prompt Construction

Pipeline in `src/agents/system-prompt.ts`:

1. `loadWorkspaceBootstrapFiles()` reads all files above
2. `buildBootstrapContextFiles()` converts to context entries with content budgeting (20KB per file, 150KB total)
3. `buildAgentSystemPrompt()` injects them into the "Project Context" section
4. Special detection: if SOUL.md exists, adds guidance: *"If SOUL.md is present, embody its persona and tone. Avoid stiff, generic replies; follow its guidance unless higher-priority instructions override it."*

## Self-Evolution Design

SOUL.md template explicitly invites mutation:
- *"This file is yours to evolve. As you learn who you are, update it."*
- *"If you change this file, tell the user -- it's your soul, and they should know."*
- *"Each session, you wake up fresh. These files ARE your memory. Read them. Update them. They're how you persist."*

Evolution cycle:
1. Daily logs capture experiences (`memory/YYYY-MM-DD.md`)
2. Periodic reviews distill learnings into `MEMORY.md`
3. Agent updates `SOUL.md` as it refines its self-understanding
4. Heartbeats can trigger memory maintenance

## SOUL.md vs state (per-chat context)

Completely separate concerns:
- **SOUL.md** = global identity, shared across all chats, persistent
- **Per-chat state** = conversation history, task context, ephemeral

## Key Design Decisions

1. **Markdown, not JSON/YAML** -- human-readable, agent-editable, no parsing needed
2. **Transparent mutation** -- agent must tell user when it changes SOUL.md
3. **Composable** -- personality is split across multiple files (soul + memory + identity), not one monolith
4. **Content-budgeted** -- files are truncated if too large (head 70% + tail 20%)
5. **Session-type aware** -- subagent sessions get minimal set (AGENTS, TOOLS, SOUL, IDENTITY, USER)

## Implications for opentlawpy

When we revisit (Phase 3+ after tools exist):
- Replace hardcoded `SYSTEM_PROMPT` with `soul.md` file loaded at runtime
- Agent uses `read_file`/`write_file` tools to edit its own soul
- `state.md` (Phase 4) stays separate -- per-chat conversation context
- System prompt = base instructions + soul.md + per-chat state context
