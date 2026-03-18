# Claude (Anthropic) Integration Guide

## Overview

This guide explains how to integrate Claude as your LLM provider in the openpaw system. Claude is Anthropic's AI assistant, offering powerful language models with large context windows (200K tokens) - perfect for agent workflows with extensive state.

---

## Table of Contents

1. [API Key Management](#api-key-management)
2. [LLM Provider Configuration](#llm-provider-configuration)
3. [Claude Client Implementation](#claude-client-implementation)
4. [Model Selection](#model-selection)
5. [Best Practices](#best-practices)
6. [Cost Optimization](#cost-optimization)
7. [Fallback Configuration](#fallback-configuration)

---

## API Key Management

### Secure Storage

**File:** `.env`

```bash
# Claude API Key
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Alternative: Use multiple keys for different projects
ANTHROPIC_API_KEY_PRIMARY=sk-ant-api03-...
ANTHROPIC_API_KEY_FALLBACK=sk-ant-api03-...

# Temporal
TEMPORAL_ADDRESS=localhost:7233

# WhatsApp (if using Green API)
GREEN_API_INSTANCE_ID=1101000001
GREEN_API_TOKEN=your-green-api-token
```

**Important:**
- ✅ Add `.env` to `.gitignore`
- ✅ Never commit API keys to git
- ✅ Use different keys for dev/production
- ✅ Rotate keys periodically

### .gitignore

```bash
# .gitignore
.env
.env.local
.env.production

# State files
state/
workspace/

# Auth files
whatsapp-auth/
baileys-bridge/auth_info/
```

---

## LLM Provider Configuration

### Configuration File

**File:** `config/llm_providers.yaml`

```yaml
# LLM Provider Configuration
providers:
  # Claude (Anthropic) - Primary
  - provider: anthropic
    model: claude-opus-4
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 4096
    temperature: 0.7
    priority: 1  # Highest priority

  # Claude Sonnet (Faster/Cheaper fallback)
  - provider: anthropic
    model: claude-sonnet-4
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 4096
    temperature: 0.7
    priority: 2  # Fallback

  # OpenAI (Secondary fallback)
  - provider: openai
    model: gpt-4
    api_key_env: OPENAI_API_KEY
    max_tokens: 4096
    temperature: 0.7
    priority: 3  # Last resort

# Default settings
default:
  provider: anthropic
  model: claude-opus-4
  timeout_seconds: 120
  max_retries: 3
```

---

## Claude Client Implementation

### LLM Client Interface

**File:** `src/llm/base.py`

```python
"""Base LLM client interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class LLMMessage:
    """Standard message format."""
    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class LLMResponse:
    """Standard LLM response."""
    content: str
    model: str
    usage: Dict[str, int]  # tokens used
    finish_reason: str
    tool_calls: List[Dict[str, Any]] = None


class LLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> LLMResponse:
        """Send chat completion request."""
        pass
```

---

### Claude Client Implementation

**File:** `src/llm/anthropic_client.py`

```python
"""Anthropic (Claude) client implementation."""
import os
from typing import List, Dict, Any, Optional
import anthropic
from anthropic.types import Message, ContentBlock
import logging

from .base import LLMClient, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClient):
    """
    Claude API client using Anthropic SDK.

    Supports:
    - Claude Opus 4, Sonnet 4, Haiku 3.5
    - Tool use (function calling)
    - Large context windows (200K tokens)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-opus-4",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        """
        Initialize Claude client.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Model name (claude-opus-4, claude-sonnet-4, etc.)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Initialize Anthropic client
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)

        logger.info(f"Initialized Claude client with model: {model}")

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat completion request to Claude.

        Args:
            messages: List of messages
            tools: Optional list of tool definitions
            **kwargs: Additional parameters

        Returns:
            LLMResponse with Claude's response
        """
        # Convert messages to Anthropic format
        claude_messages = self._convert_messages(messages)

        # Extract system message (Claude handles it separately)
        system_message = None
        if claude_messages and claude_messages[0]["role"] == "system":
            system_message = claude_messages[0]["content"]
            claude_messages = claude_messages[1:]

        try:
            # Build request parameters
            request_params = {
                "model": self.model,
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
                "messages": claude_messages,
            }

            # Add system message if present
            if system_message:
                request_params["system"] = system_message

            # Add tools if provided
            if tools:
                request_params["tools"] = self._convert_tools(tools)

            # Call Claude API
            logger.debug(f"Calling Claude API with {len(claude_messages)} messages")
            response: Message = await self.client.messages.create(**request_params)

            # Parse response
            return self._parse_response(response)

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Claude: {e}", exc_info=True)
            raise

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, str]]:
        """Convert standard messages to Claude format."""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

    def _convert_tools(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert OpenAI-style tool definitions to Claude format.

        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {...}
            }
        }

        Claude format:
        {
            "name": "get_weather",
            "description": "Get weather",
            "input_schema": {...}
        }
        """
        claude_tools = []

        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                claude_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })
            else:
                # Already in Claude format
                claude_tools.append(tool)

        return claude_tools

    def _parse_response(self, response: Message) -> LLMResponse:
        """Parse Claude API response into standard format."""
        # Extract text content
        content = ""
        tool_calls = []

        for block in response.content:
            if isinstance(block, ContentBlock):
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    })

        # Build usage info
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
            finish_reason=response.stop_reason,
            tool_calls=tool_calls if tool_calls else None,
        )


# Factory function
def create_anthropic_client(
    api_key: Optional[str] = None,
    model: str = "claude-opus-4",
    **kwargs
) -> AnthropicClient:
    """Create Anthropic client instance."""
    return AnthropicClient(
        api_key=api_key,
        model=model,
        **kwargs
    )
```

---

### LLM Registry (Multi-Provider Support)

**File:** `src/llm/registry.py`

```python
"""LLM provider registry with fallback support."""
from typing import List, Optional, Dict, Any
import logging
from enum import Enum

from .base import LLMClient, LLMMessage, LLMResponse
from .anthropic_client import create_anthropic_client
from .openai_client import create_openai_client  # If you have OpenAI fallback

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    LOCAL = "local"


class LLMRegistry:
    """
    Manages multiple LLM providers with automatic fallback.

    Tries providers in priority order:
    1. Claude Opus (primary)
    2. Claude Sonnet (faster/cheaper)
    3. OpenAI GPT-4 (last resort)
    """

    def __init__(self, configs: List[Dict[str, Any]]):
        """
        Initialize registry with provider configs.

        Args:
            configs: List of provider configurations
                    [
                        {
                            "provider": "anthropic",
                            "model": "claude-opus-4",
                            "api_key_env": "ANTHROPIC_API_KEY",
                            "priority": 1
                        },
                        ...
                    ]
        """
        # Sort by priority (lower number = higher priority)
        self.configs = sorted(configs, key=lambda c: c.get("priority", 999))
        self.clients: List[LLMClient] = []
        self.current_index = 0

        # Initialize all clients
        for config in self.configs:
            client = self._create_client(config)
            if client:
                self.clients.append(client)

        if not self.clients:
            raise ValueError("No LLM clients could be initialized")

        logger.info(f"Initialized {len(self.clients)} LLM providers")

    def _create_client(self, config: Dict[str, Any]) -> Optional[LLMClient]:
        """Create client from config."""
        provider = config.get("provider")

        try:
            if provider == "anthropic":
                import os
                api_key = os.getenv(config.get("api_key_env", "ANTHROPIC_API_KEY"))

                return create_anthropic_client(
                    api_key=api_key,
                    model=config.get("model", "claude-opus-4"),
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.7),
                )

            elif provider == "openai":
                # Similar for OpenAI
                return create_openai_client(config)

            else:
                logger.warning(f"Unknown provider: {provider}")
                return None

        except Exception as e:
            logger.error(f"Failed to create {provider} client: {e}")
            return None

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Send chat request with automatic fallback.

        Tries providers in priority order until success.
        """
        last_error = None

        for i, client in enumerate(self.clients):
            try:
                logger.debug(f"Trying provider {i+1}/{len(self.clients)}")

                response = await client.chat(messages, tools, **kwargs)

                # Success!
                if i > 0:
                    logger.warning(f"Used fallback provider (index {i})")

                return response

            except Exception as e:
                logger.warning(f"Provider {i} failed: {e}")
                last_error = e

                # Try next provider
                continue

        # All providers failed
        raise Exception(f"All LLM providers failed. Last error: {last_error}")

    def get_primary_model(self) -> str:
        """Get primary model name."""
        if self.clients:
            return self.clients[0].model
        return "unknown"


# Global registry instance
_registry: Optional[LLMRegistry] = None


def get_llm_registry() -> LLMRegistry:
    """Get global LLM registry instance."""
    global _registry

    if _registry is None:
        # Load from config
        import yaml
        import os

        config_path = os.getenv("LLM_CONFIG_PATH", "config/llm_providers.yaml")

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            _registry = LLMRegistry(config["providers"])

        except Exception as e:
            logger.error(f"Failed to load LLM config: {e}")

            # Fallback: Use environment variables
            import os
            configs = []

            if os.getenv("ANTHROPIC_API_KEY"):
                configs.append({
                    "provider": "anthropic",
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-opus-4"),
                    "api_key_env": "ANTHROPIC_API_KEY",
                    "priority": 1,
                })

            if os.getenv("OPENAI_API_KEY"):
                configs.append({
                    "provider": "openai",
                    "model": os.getenv("OPENAI_MODEL", "gpt-4"),
                    "api_key_env": "OPENAI_API_KEY",
                    "priority": 2,
                })

            if not configs:
                raise ValueError("No LLM API keys found in environment")

            _registry = LLMRegistry(configs)

    return _registry
```

---

### LLM Call Activity (Updated)

**File:** `src/activities/llm_call.py`

```python
"""LLM call activity using Claude."""
from temporalio import activity
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import logging

from src.llm.registry import get_llm_registry
from src.llm.base import LLMMessage

logger = logging.getLogger(__name__)


@dataclass
class LLMCallInput:
    """Input for LLM call activity."""
    messages: List[Dict[str, str]]  # [{"role": "user", "content": "..."}]
    tools: Optional[List[Dict]] = None
    max_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class LLMCallOutput:
    """Output from LLM call."""
    content: str
    model: str
    usage: Dict[str, int]
    tool_calls: Optional[List[Dict]] = None


@activity.defn
async def call_llm_activity(input: LLMCallInput) -> LLMCallOutput:
    """
    Call LLM (Claude) with automatic fallback.

    Args:
        input: LLM call parameters

    Returns:
        LLM response
    """
    activity.logger.info(f"Calling LLM with {len(input.messages)} messages")

    try:
        # Get LLM registry (handles fallback)
        registry = get_llm_registry()

        # Convert messages to LLMMessage objects
        messages = [
            LLMMessage(role=msg["role"], content=msg["content"])
            for msg in input.messages
        ]

        # Call LLM
        response = await registry.chat(
            messages=messages,
            tools=input.tools,
            max_tokens=input.max_tokens,
            temperature=input.temperature,
        )

        activity.logger.info(
            f"LLM response received: {response.usage['total_tokens']} tokens"
        )

        return LLMCallOutput(
            content=response.content,
            model=response.model,
            usage=response.usage,
            tool_calls=response.tool_calls,
        )

    except Exception as e:
        activity.logger.error(f"LLM call failed: {e}", exc_info=True)
        raise
```

---

## Model Selection

### Available Claude Models

| Model | Context | Speed | Cost | Best For |
|-------|---------|-------|------|----------|
| **claude-opus-4** | 200K | Slow | $$$$ | Complex reasoning |
| **claude-sonnet-4** | 200K | Medium | $$ | Balanced |
| **claude-haiku-3.5** | 200K | Fast | $ | Simple tasks |

### Model Selection Strategy

**File:** `src/llm/model_selector.py`

```python
"""Smart model selection based on task complexity."""
from typing import List, Dict


def select_claude_model(
    conversation_length: int,
    has_tools: bool,
    requires_reasoning: bool,
) -> str:
    """
    Select appropriate Claude model based on task.

    Args:
        conversation_length: Number of messages in conversation
        has_tools: Whether tools are being used
        requires_reasoning: Whether complex reasoning is needed

    Returns:
        Model name
    """
    # Complex reasoning → Opus
    if requires_reasoning or has_tools:
        return "claude-opus-4"

    # Long conversation → Sonnet (cheaper for large context)
    if conversation_length > 10:
        return "claude-sonnet-4"

    # Simple tasks → Haiku (fastest, cheapest)
    return "claude-haiku-3.5"


# Usage in workflow
model = select_claude_model(
    conversation_length=len(messages),
    has_tools=True,
    requires_reasoning=True,
)
```

---

## Best Practices

### 1. System Prompts for Claude

Claude responds well to clear, structured prompts:

```python
CLAUDE_SYSTEM_PROMPT = """You are a helpful AI assistant with the following capabilities:

<capabilities>
- Execute bash commands
- Read and write files
- Search your memory
- Send messages via WhatsApp
</capabilities>

<guidelines>
1. Be concise and helpful
2. Ask clarifying questions when needed
3. Use tools when appropriate
4. Maintain context from state.md
</guidelines>

<state>
{state_content}
</state>

Remember to update state.md with important information after each interaction.
"""
```

### 2. Context Window Management

Claude has 200K token context - use it wisely:

```python
async def _prepare_messages(self) -> List[LLMMessage]:
    """Prepare messages for Claude with full context."""

    messages = []

    # System prompt with state.md (use full context!)
    system_content = CLAUDE_SYSTEM_PROMPT.format(
        state_content=self.state_content  # Include entire state.md
    )
    messages.append(LLMMessage(role="system", content=system_content))

    # Recent conversation (last 50 messages)
    recent_messages = self.state.conversation.messages[-50:]

    for msg in recent_messages:
        messages.append(LLMMessage(
            role=msg.role.value,
            content=msg.content
        ))

    return messages
```

### 3. Tool Use with Claude

Claude excels at tool use. Define tools clearly:

```python
BASH_TOOL = {
    "name": "execute_bash",
    "description": """Execute a bash command and return the output.

Use this when you need to:
- Check system information
- Run scripts
- Manage files
- Install packages

Always verify the command is safe before executing.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 300)"
            }
        },
        "required": ["command"]
    }
}
```

### 4. Error Handling

```python
from anthropic import (
    APIError,
    RateLimitError,
    APITimeoutError,
    InternalServerError,
)

try:
    response = await claude_client.chat(messages, tools)

except RateLimitError as e:
    # Wait and retry
    logger.warning("Rate limit hit, waiting...")
    await asyncio.sleep(60)
    # Retry logic here

except APITimeoutError as e:
    # Reduce max_tokens and retry
    logger.warning("Timeout, reducing tokens...")
    # Retry with smaller max_tokens

except InternalServerError as e:
    # Temporary server issue, retry
    logger.error("Claude server error, retrying...")
    # Retry logic

except APIError as e:
    # Other API errors
    logger.error(f"Claude API error: {e}")
    raise
```

---

## Cost Optimization

### Current Pricing (2026 Estimates)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| **Opus 4** | $15 | $75 |
| **Sonnet 4** | $3 | $15 |
| **Haiku 3.5** | $0.80 | $4 |

### Cost Tracking

```python
# src/utils/cost_tracker.py
"""Track LLM costs."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LLMUsage:
    """Track LLM usage and cost."""
    model: str
    prompt_tokens: int
    completion_tokens: int
    timestamp: datetime

    def calculate_cost(self) -> float:
        """Calculate cost in USD."""
        # Prices per 1M tokens
        prices = {
            "claude-opus-4": {"input": 15.0, "output": 75.0},
            "claude-sonnet-4": {"input": 3.0, "output": 15.0},
            "claude-haiku-3.5": {"input": 0.80, "output": 4.0},
        }

        if self.model not in prices:
            return 0.0

        price = prices[self.model]

        input_cost = (self.prompt_tokens / 1_000_000) * price["input"]
        output_cost = (self.completion_tokens / 1_000_000) * price["output"]

        return input_cost + output_cost


# Usage in activity
usage = LLMUsage(
    model=response.model,
    prompt_tokens=response.usage["prompt_tokens"],
    completion_tokens=response.usage["completion_tokens"],
    timestamp=datetime.utcnow(),
)

cost = usage.calculate_cost()
activity.logger.info(f"LLM call cost: ${cost:.4f}")
```

### Optimization Strategies

1. **Use Haiku for simple tasks:**
   ```python
   if is_simple_query(message):
       model = "claude-haiku-3.5"  # 5x cheaper
   ```

2. **Cache system prompts** (when Anthropic releases prompt caching):
   ```python
   # Future: Prompt caching can reduce costs by 90%
   # for repeated system prompts
   ```

3. **Summarize old conversations:**
   ```python
   if len(conversation) > 100:
       # Summarize old messages, keep recent ones
       summary = await summarize_conversation(old_messages)
   ```

4. **Limit context window:**
   ```python
   # Don't send entire state.md if not needed
   if task_is_simple:
       # Send only recent state, not full history
       pass
   ```

---

## Fallback Configuration

### Multi-Provider Setup

**Recommended fallback chain:**
1. Claude Opus 4 (primary - best quality)
2. Claude Sonnet 4 (fallback - faster/cheaper)
3. GPT-4 (last resort - different provider)

**File:** `config/llm_providers.yaml`

```yaml
providers:
  # Primary: Claude Opus
  - provider: anthropic
    model: claude-opus-4
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 4096
    temperature: 0.7
    priority: 1
    retry_on:
      - rate_limit
      - timeout
      - server_error

  # Fallback 1: Claude Sonnet
  - provider: anthropic
    model: claude-sonnet-4
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 4096
    temperature: 0.7
    priority: 2

  # Fallback 2: OpenAI (optional)
  - provider: openai
    model: gpt-4-turbo
    api_key_env: OPENAI_API_KEY
    max_tokens: 4096
    temperature: 0.7
    priority: 3

# Retry configuration
retry:
  max_attempts: 3
  initial_delay: 1  # seconds
  max_delay: 60
  backoff_factor: 2
```

### Retry Logic

```python
from temporalio.common import RetryPolicy
from datetime import timedelta

# In workflow
llm_response = await workflow.execute_activity(
    call_llm_activity,
    LLMCallInput(messages=messages, tools=tools),
    start_to_close_timeout=timedelta(seconds=120),
    retry_policy=RetryPolicy(
        maximum_attempts=3,
        initial_interval=timedelta(seconds=1),
        maximum_interval=timedelta(seconds=60),
        backoff_coefficient=2.0,
        non_retryable_error_types=["InvalidRequestError"],
    )
)
```

---

## Testing

### Unit Test

```python
# tests/test_anthropic_client.py
import pytest
from src.llm.anthropic_client import AnthropicClient
from src.llm.base import LLMMessage


@pytest.mark.asyncio
async def test_claude_chat():
    """Test Claude client."""
    client = AnthropicClient(model="claude-sonnet-4")

    messages = [
        LLMMessage(role="user", content="What is 2+2?")
    ]

    response = await client.chat(messages)

    assert "4" in response.content
    assert response.model == "claude-sonnet-4"
    assert response.usage["total_tokens"] > 0


@pytest.mark.asyncio
async def test_claude_with_tools():
    """Test Claude with tool use."""
    client = AnthropicClient()

    tools = [
        {
            "name": "get_weather",
            "description": "Get weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        }
    ]

    messages = [
        LLMMessage(role="user", content="What's the weather in SF?")
    ]

    response = await client.chat(messages, tools=tools)

    # Claude should call the tool
    assert response.tool_calls is not None
    assert len(response.tool_calls) > 0
    assert response.tool_calls[0]["name"] == "get_weather"
```

---

## Environment Setup

### Development

```bash
# .env.development
ANTHROPIC_API_KEY=sk-ant-api03-dev-key...
ANTHROPIC_MODEL=claude-haiku-3.5  # Cheaper for dev
TEMPORAL_ADDRESS=localhost:7233
```

### Production

```bash
# .env.production
ANTHROPIC_API_KEY=sk-ant-api03-prod-key...
ANTHROPIC_MODEL=claude-opus-4  # Best quality
TEMPORAL_ADDRESS=temporal.production.internal:7233
```

### Docker Compose

```yaml
services:
  worker:
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-claude-opus-4}
    # ...
```

---

## Monitoring

### Log API Usage

```python
import logging

logger = logging.getLogger("llm_usage")

# After each LLM call
logger.info(
    "llm_call",
    extra={
        "model": response.model,
        "prompt_tokens": response.usage["prompt_tokens"],
        "completion_tokens": response.usage["completion_tokens"],
        "total_tokens": response.usage["total_tokens"],
        "cost_usd": calculate_cost(response),
    }
)
```

### Daily Cost Summary

```python
# scripts/daily_cost_summary.py
"""Generate daily cost summary."""
import json
from datetime import datetime, timedelta
from collections import defaultdict

def summarize_costs(log_file: str):
    """Parse logs and summarize costs."""
    costs = defaultdict(float)

    with open(log_file) as f:
        for line in f:
            if "llm_call" in line:
                data = json.loads(line)
                date = data["timestamp"][:10]  # YYYY-MM-DD
                costs[date] += data["cost_usd"]

    for date, cost in sorted(costs.items()):
        print(f"{date}: ${cost:.2f}")

    print(f"Total: ${sum(costs.values()):.2f}")
```

---

## Quick Start

### 1. Get API Key

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create account or log in
3. Generate API key
4. Copy to `.env` file

### 2. Install SDK

```bash
pip install anthropic
```

### 3. Test Connection

```python
# test_claude.py
import asyncio
from anthropic import AsyncAnthropic

async def test():
    client = AsyncAnthropic()

    message = await client.messages.create(
        model="claude-opus-4",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": "Hello, Claude!"}
        ]
    )

    print(message.content[0].text)

asyncio.run(test())
```

### 4. Run Test

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
python test_claude.py
```

---

## Summary

**To use Claude with your openpaw system:**

1. ✅ Add `ANTHROPIC_API_KEY` to `.env`
2. ✅ Install `anthropic` Python package
3. ✅ Use the `AnthropicClient` implementation above
4. ✅ Configure fallback in `llm_providers.yaml`
5. ✅ Monitor costs with usage tracking

**Advantages of Claude:**
- ✅ 200K token context (perfect for large state.md)
- ✅ Excellent at tool use
- ✅ Strong reasoning capabilities
- ✅ Good at following instructions

**Best Practices:**
- Use Opus for complex reasoning
- Use Sonnet for most tasks
- Use Haiku for simple queries
- Track costs to avoid surprises
- Set up fallback to Sonnet/GPT-4

You're ready to build! 🚀
