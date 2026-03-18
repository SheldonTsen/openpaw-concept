# openpaw

A WhatsApp-integrated agentic system built with Temporal orchestration and neonize.

Inspired by [OpenClaw](https://github.com/openclaw) — but in Python, and using Temporal instead of custom orchestration.

> **Name origin**: Openclaw → Open**t**law (Temporal) → Open**t**law**py** (Python). Yeah...

## Quick Start (Prod)

```
cp .env.example .env
# fill in required details mainly API key and whatsapp phone number

docker compose up --build

docker compose logs listener # scan the bar code to link to whatsapp
```

## Quick Start (Dev)


```
cp .env.example .env
# fill in required details mainly API key and whatsapp phone number

# alternatively - if you don't have a paid API key, use OpenRouter
OPENROUTER_API_KEY=...
LLM_MODEL=openrouter/free

# alternatively - run scripts/start-mlx-server.sh for a local model if you machine can handle it. Don't forget to set .env appropriately ie
LLM_MODEL=  # yes leave blank
LLM_PROVIDER=local
LOCAL_MODEL_URL=http://host.docker.internal:8888/v1

# terminal 1
docker compose -f docker-compose.yaml -f docker-compose.dev.yml watch --remove-orphans

# terminal 2
docker compose logs -f worker listener
```

## Local CLI 

If you're not using WhatsApp, then you can also boot up a local terminal session:
```
openpaw-terminal
```



## Architecture

```
WhatsApp <-> Neonize (WebSocket) <-> Listener <-> Temporal <-> Worker
                                                                 |
                                                           LLM / Tools
                                                                 |
                                                           state.md files
```

1. **Neonize Listener** connects to WhatsApp as a linked device, receives messages via event callbacks
2. **Temporal Workflow** orchestrates the agent loop: receive message -> call LLM -> execute tools -> respond
3. **State files** (`state.md`) persist conversation history and agent context per chat

See [docs/plan.md](docs/plan.md) for the full architecture and implementation plan.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- `brew install libmagic` (required by neonize)

### Setup

```bash
# 1. Clone and configure
git clone git@github.com:SheldonTsen/openpaw.git
cd openpaw
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 2. Start all services
docker-compose up -d

# 3. Link WhatsApp (first run only)
# View listener logs for QR code:
docker-compose logs -f whatsapp-listener
# Scan QR with WhatsApp -> Settings -> Linked Devices -> Link a Device
# Auth persists in neonize.db — subsequent runs reconnect automatically

# 4. Send a WhatsApp message to the linked number
```

### Environment Variables

Required:
- `ANTHROPIC_API_KEY` — for Claude LLM calls

Optional:
- `TEMPORAL_ADDRESS` — defaults to `localhost:7233`
- `NEONIZE_DB_PATH` — defaults to `./neonize.db`
- `LLM_MODEL` — defaults to `claude-sonnet-4.5`

## Development

```bash
# Start dev environment (hot reload enabled)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f worker whatsapp-listener

# Run a single test
docker-compose run --rm pytest tests/test_llm.py::test_call_llm -v

# View agent state files directly on host
cat ./state/whatsapp-*/state.md

# Stop
docker-compose down
```

### Code Quality

```bash
source .venv/bin/activate

# Format
ruff check --fix .

# Type check
ty check

# Run tests locally
pytest tests/ -v
```

### When to Rebuild

Only rebuild if you changed `requirements.txt`, `Dockerfile`, or system dependencies.
Python code changes are picked up automatically via hot reload.

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build worker
docker-compose restart worker
```
