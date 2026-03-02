import anthropic

from opentlawpy.models.llm import LLMCallOutput


class AnthropicClient:
    def __init__(self, *, api_key: str, base_url: str = None):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.AsyncAnthropic(**kwargs)

    async def chat(self, *, messages: list[dict], model: str, max_tokens: int) -> LLMCallOutput:
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return LLMCallOutput(
            response_text=response.content[0].text,
            model_used=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
