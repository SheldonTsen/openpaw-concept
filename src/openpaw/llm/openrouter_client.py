import json
import logging

import httpx

from openpaw.config import LLM_TIMEOUT_SECONDS
from openpaw.models.llm_call import LLMCallOutput

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


def _parse_tool_calls(raw_tool_calls: list[dict] | None) -> list[dict]:
    """Parse tool_calls from OpenAI format, converting arguments JSON string to dict."""
    if not raw_tool_calls:
        return []

    parsed = []
    for tc in raw_tool_calls:
        arguments = tc["function"]["arguments"]
        if isinstance(arguments, str):
            arguments = json.loads(arguments)

        parsed.append(
            {
                "id": tc["id"],
                "type": tc["type"],
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": arguments,
                },
            }
        )
    return parsed


def _serialize_messages(messages: list[dict]) -> list[dict]:
    """Serialize tool_calls arguments back to JSON strings for the OpenAI API format."""
    serialized = []
    for msg in messages:
        if "tool_calls" not in msg:
            serialized.append(msg)
            continue

        serialized.append(
            {
                **msg,
                "tool_calls": [
                    {
                        **tc,
                        "function": {
                            **tc["function"],
                            "arguments": json.dumps(tc["function"]["arguments"])
                            if isinstance(tc["function"]["arguments"], dict)
                            else tc["function"]["arguments"],
                        },
                    }
                    for tc in msg["tool_calls"]
                ],
            }
        )
    return serialized


class OpenRouterClient:
    def __init__(self, *, api_key: str):
        self._api_key = api_key

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
        max_tokens: int,
        tools: list[dict] | None = None,
    ) -> LLMCallOutput:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": model,
            "messages": _serialize_messages(messages),
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        logger.debug("OpenRouter payload: payload=%s", payload)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=OPENROUTER_BASE_URL,
                headers=headers,
                json=payload,
                timeout=LLM_TIMEOUT_SECONDS,
            )
            if not response.is_success:
                logger.error("OpenRouter API error %s: %s", response.status_code, response.text)
            response.raise_for_status()
            data = response.json()

        logger.debug("OpenRouter response: data=%s", data)

        choice = data["choices"][0]
        message = choice["message"]
        usage = data.get("usage", {})

        logger.info("OpenRouter response: choice=%s usage=%s", choice, usage)

        tool_calls = _parse_tool_calls(message.get("tool_calls"))
        finish_reason = choice.get("finish_reason")

        return LLMCallOutput(
            response_text=message.get("content") or "",
            model_used=data.get("model", model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            tool_calls=tool_calls,
            stop_reason=finish_reason,
        )
