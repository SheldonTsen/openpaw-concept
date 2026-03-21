
# Codestyle

Always prefer calling functions using kwargs whenever possible. This
might not be possible with temporal however. Use ruff for formatting and ty for type checking.

uv is used for package management.

Do NOT put logic in `__init__.py` files — keep them empty. Use dedicated modules instead (e.g. `activities/create_activities.py` not `activities/__init__.py`).

# Development Rules

Build small, one at a time. For each new functionality, create a new branch, write the code for that feature, add the tests, and run the tests to check.
When ready, commit the work.

As you develop, update docs/developer/execution-list.md to keep track of what you've done.
If we discover something, update the docs/developer/execution-list.md in the appropriate place.

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
