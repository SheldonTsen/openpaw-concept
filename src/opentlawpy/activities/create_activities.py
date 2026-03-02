from opentlawpy.activities.llm_call import create_call_llm_activity
from opentlawpy.config import ANTHROPIC_API_KEY
from opentlawpy.llm.anthropic_client import AnthropicClient


def create_activities() -> list:
    anthropic_client = AnthropicClient(api_key=ANTHROPIC_API_KEY)
    return [
        create_call_llm_activity(anthropic_client=anthropic_client),
    ]
