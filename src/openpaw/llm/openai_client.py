import json
import logging

import httpx

from openpaw.config import LLM_TIMEOUT_SECONDS
from openpaw.models.llm_call import LLMCallOutput

logger = logging.getLogger(__name__)


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


class OpenAIClient:
    """Generic client for any OpenAI-compatible API (MLX LM server, vLLM, etc.)."""

    def __init__(self, *, base_url: str, api_key: str = None, timeout: float = LLM_TIMEOUT_SECONDS):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
        max_tokens: int,
        tools: list[dict] | None = None,
    ) -> LLMCallOutput:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: dict = {
            "messages": _serialize_messages(messages),
        }
        if model:
            payload["model"] = model
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        logger.debug("OpenAI-compatible payload: payload=%s", payload)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
            if not response.is_success:
                logger.error(
                    "OpenAI-compatible API error %s: %s",
                    response.status_code,
                    response.text,
                )
            response.raise_for_status()
            data = response.json()

        logger.debug("OpenAI-compatible response: data=%s", data)

        choice = data["choices"][0]
        message = choice["message"]
        usage = data.get("usage", {})

        logger.info("OpenAI-compatible response: choice=%s usage=%s", choice, usage)

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
