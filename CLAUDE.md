
# Codestyle

Always prefer calling functions using kwargs whenever possible. This 
might not be possible with temporal however. Use ruff for formatting and ty for type checking. 

uv is used for package management. 

# Development Rules

Build small, one at a time. For each new functionality, create a new branch, write the code for that feature, add the tests, and run the tests to check.
When ready, commit the work.

As you develop, update execution-list.md to keep track of what you've done.
If we discover something, update the execution-list.md in the appropriate place. 

# Misc

Update this file yourself as you receive pattern instructions or DO or DO NOTs.

---

# Token-Saving Iteration Workflow

## The Golden Rule
**Build once, iterate fast. Don't rebuild unless dependencies change.**

## Daily Development Loop

```bash
# ✅ Morning: Start services (once)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# ✅ Edit code → auto-reload (no rebuild needed!)
vim src/workflows/agent_workflow.py
# Worker automatically restarts via watchdog

# ✅ View logs to confirm reload
docker-compose logs -f worker --tail=20

# ✅ Run single test (fast!)
docker-compose run --rm pytest tests/test_llm.py::test_call_llm -v

# ✅ View state files directly (no docker exec!)
cat ./state/whatsapp-123456/state.md
ls -la ./workspace/

# ✅ Evening: Stop
docker-compose down
```

## When to Rebuild (Rare!)

Only rebuild if you changed:
- ✅ `requirements.txt` (new Python package)
- ✅ `Dockerfile` or `Dockerfile.dev`
- ✅ System dependencies (apt packages)

**Do NOT rebuild for:**
- ❌ Python code changes (hot reload handles it!)
- ❌ Tool definition changes (loaded fresh each run)
- ❌ Configuration changes (mount as volume)

```bash
# Only when necessary:
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build worker
docker-compose restart worker
```

---

# Testing Strategy

## Run Specific Tests (Fastest)

```bash
# Single test function (10-30 seconds)
docker-compose run --rm pytest tests/test_llm.py::test_anthropic_client -v

# Single test file (30-60 seconds)
docker-compose run --rm pytest tests/test_activities/test_bash_executor.py -v

# Single test module (1-2 minutes)
docker-compose run --rm pytest tests/test_activities/ -v
```

## Test Categories

```bash
# Unit tests (fast - 2-3 minutes)
pytest tests/test_activities/ tests/test_models/ -v

# Integration tests (medium - 5-10 minutes)
pytest tests/test_integration/ -v

# End-to-end tests (slow - 10-20 minutes)
pytest tests/test_integration/test_e2e_whatsapp.py -v

# Coverage report
pytest --cov=src --cov-report=term-missing tests/
```

## Testing Best Practices

**1. Test what you changed:**
```bash
# ❌ Slow: Run all 50+ tests
pytest tests/

# ✅ Fast: Run only related tests
pytest tests/test_activities/test_llm_call.py -v
```

**2. Use verbose output for debugging:**
```bash
# See test names and progress
pytest tests/ -v

# See print statements
pytest tests/ -v -s

# Stop on first failure
pytest tests/ -x
```

---

# Debugging

## View Real-Time Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f worker

# Last 50 lines + follow
docker-compose logs -f worker --tail=50

# Multiple services
docker-compose logs -f worker whatsapp-poller
```

## Inspect State Files

```bash
# List all agent states
ls -la ./state/

# View specific agent state
cat ./state/whatsapp-1234567890@c.us/state.md

# Watch state file changes
watch -n 1 cat ./state/whatsapp-*/state.md

# Check workspace files
ls -la ./workspace/
```

## Temporal UI

```bash
# Open Temporal UI
open http://localhost:8080

# View workflow history:
# 1. Click "Workflows" in sidebar
# 2. Search by workflow ID: "whatsapp-1234567890@c.us"
# 3. View execution history, activities, signals
```

## Shell Into Worker

```bash
# Interactive shell
docker-compose exec worker bash

# Check Python environment
docker-compose exec worker python -c "import temporalio; print(temporalio.__version__)"
```

---

# Quick Reference Commands

## Development
```bash
# Start dev environment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f worker whatsapp-poller

# Run single test
docker-compose run --rm pytest tests/test_llm.py::test_call_llm -v

# View state files
cat ./state/whatsapp-*/state.md

# Restart worker only
docker-compose restart worker
```

## Testing
```bash
# Unit tests
pytest tests/test_activities/ -v

# Coverage
pytest --cov=src --cov-report=term-missing

# Single test
pytest tests/test_llm.py::test_anthropic_client -v
```

## Production
```bash
# Start
docker-compose up -d

# Status
docker-compose ps

# Stop
docker-compose down
```

