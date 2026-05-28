
## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```


# Codestyle

Always prefer calling functions using kwargs whenever possible. This
might not be possible with temporal however. Use ruff for formatting.

uv is used for package management.

Do NOT put logic in `__init__.py` files — keep them empty. Use dedicated modules instead (e.g. `activities/create_activities.py` not `activities/__init__.py`).

# Development Rules

Build small, one at a time. For each new functionality, create a new branch, write the code for that feature, add the tests, and run the tests to check.
When ready, commit the work.

As you develop, update docs/developer/execution-list.md to keep track of what you've done.
If we discover something, update the docs/developer/execution-list.md in the appropriate place.

# Documentation

Ensure we update docs/user with features on how to use openpaw. 

# Misc

Update this file yourself as you receive pattern instructions or DO or DO NOTs.

---

# Development

## Daily Loop

```bash
# Start services (once)
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml watch --remove-orphans

# View logs
docker compose logs -f worker whatsapp-listener

# View agent state files
cat ./data/state/*/state.json

# Restart worker only
docker compose restart worker
```

## When to Rebuild

Only rebuild if you changed `pyproject.toml` (new package), `Dockerfile`, or system dependencies.

```bash
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml build worker
docker compose restart worker
```

---

# Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Single test
uv run pytest tests/test_activities/test_llm_call.py -v

# Coverage
uv run pytest --cov=src --cov-report=term-missing tests/
```

---

# Debugging

## Logs

```bash
docker compose logs -f worker
docker compose logs -f worker --tail=50
```

## Temporal UI

```
http://localhost:8080  →  select "openpaw" namespace
```

## Shell Into Worker

```bash
docker compose exec worker bash
```
