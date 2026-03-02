from opentlawpy.activities.llm_call import create_call_llm_activity
from opentlawpy.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    LLM_PROVIDER,
    OPENROUTER_API_KEY,
)


def create_activities() -> list:
    if LLM_PROVIDER == "anthropic":
        from opentlawpy.llm.anthropic_client import AnthropicClient

        llm_client = AnthropicClient(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    else:
        from opentlawpy.llm.openrouter_client import OpenRouterClient

        llm_client = OpenRouterClient(api_key=OPENROUTER_API_KEY)

    return [
        create_call_llm_activity(llm_client=llm_client),
    ]
