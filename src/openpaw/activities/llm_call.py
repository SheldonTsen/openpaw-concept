from typing import Any, Callable

from temporalio import activity

from openpaw.models.llm_call import LLMCallInput, LLMCallOutput


def create_call_llm_activity(*, llm_client: Any) -> Callable:
    @activity.defn(name="call_llm")
    async def call_llm(input: LLMCallInput) -> LLMCallOutput:
        return await llm_client.chat(
            messages=input.messages,
            model=input.model,
            max_tokens=input.max_tokens,
            tools=input.tools,
        )

    return call_llm
