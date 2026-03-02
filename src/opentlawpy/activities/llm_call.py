from typing import Callable

from temporalio import activity

from opentlawpy.llm.anthropic_client import AnthropicClient
from opentlawpy.models.llm import LLMCallInput, LLMCallOutput


def create_call_llm_activity(*, anthropic_client: AnthropicClient) -> Callable:
    @activity.defn(name="call_llm")
    async def call_llm(input: LLMCallInput) -> LLMCallOutput:
        return await anthropic_client.chat(
            messages=input.messages,
            model=input.model,
            max_tokens=input.max_tokens,
        )

    return call_llm
