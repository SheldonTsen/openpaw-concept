import logging

import httpx

from opentlawpy.models.llm import LLMCallOutput

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient:
    def __init__(self, *, api_key: str):
        self._api_key = api_key

    async def chat(self, *, messages: list[dict], model: str, max_tokens: int) -> LLMCallOutput:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": model,
            "messages": messages,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=OPENROUTER_BASE_URL,
                headers=headers,
                json=payload,
                timeout=120.0,
            )
            if not response.is_success:
                logger.error("OpenRouter API error %s: %s", response.status_code, response.text)
            response.raise_for_status()
            data = response.json()

        logger.info("OpenRouter response: data=%s", data)

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMCallOutput(
            response_text=choice["message"]["content"],
            model_used=data.get("model", model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
