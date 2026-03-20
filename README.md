# openpaw

Inspired by [OpenClaw](https://github.com/openclaw) — but in Python, and using Temporal instead of custom orchestration.

Why Temporal? Because [reasons](docs/user/01-why-temporal.md).

## Prerequisites

- Docker and Docker Compose

## Minimal Quick Start

```
cp .env.example .env
# fill in required details mainly API key 

# alternatively - if you don't have a paid API key, use Ollama (easiest)
LLM_PROVIDER=local
LOCAL_MODEL_URL=https://ollama.com/v1
LOCAL_MODEL_API_KEY=...
LLM_MODEL=qwen3-coder:480b-cloud

# alternatively - run scripts/start-mlx-server.sh for a local model if you machine can handle it. Don't forget to set .env appropriately ie
LLM_MODEL=  # yes leave blank
LLM_PROVIDER=local
LOCAL_MODEL_URL=http://host.docker.internal:8888/v1

# terminal 1
docker-compose -f docker-compose.yaml -f docker-compose.dev.yaml up -d

# terminal 2
uv run openpaw
```

This will boot up a local terminal session where you can interact. 
Say "Hi!" in the terminal and watch it respond.


## Minimal Quick Start (Whatsapp)

```
cp .env.example .env
# fill in required details mainly API key and WhatsApp number
# fill in your own whatsapp number for simplicity
# you do not need a separate whatsapp number
MY_WHATSAPP_NUMBER=...

# alternatively - if you don't have a paid API key, use Ollama
# for Ollama
LLM_PROVIDER=local
LOCAL_MODEL_URL=https://ollama.com/v1
LOCAL_MODEL_API_KEY=...
LLM_MODEL=qwen3-coder:480b-cloud

# alternatively - run scripts/start-mlx-server.sh for a local model if you machine can handle it. Don't forget to set .env appropriately ie
LLM_MODEL=  # yes leave blank
LLM_PROVIDER=local
LOCAL_MODEL_URL=http://host.docker.internal:8888/v1

# terminal 1
docker-compose -f docker-compose.yaml -f docker-compose.dev.yaml up -d

# terminal 2 
docker compose logs listener
# scan the bar code to link to whatsapp

```

Say "Hi!" to it (really yourself) and watch it respond.


## Backend

Once you've interacted with the agent by sending a message, to view everything the agent does, go to http://localhost:8080/ and 
select the `openpaw` namespace (top left corner). 


## Development

```bash
# terminal 1
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml watch --remove-orphans

# terminal 2
docker compose logs -f worker whatsapp-listener

# View agent state files directly on host
cat ./data/state/*/state.json
```
