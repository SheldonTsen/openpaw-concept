import logging

from temporalio.client import Client

from opentlawpy.activities.bash_command import execute_bash_command
from opentlawpy.activities.compaction import create_compact_history_activity
from opentlawpy.activities.file_operations import read_file_activity, write_file_activity
from opentlawpy.activities.gather_tool_results import gather_tool_results_activity
from opentlawpy.activities.llm_call import create_call_llm_activity
from opentlawpy.activities.poke_agent import create_poke_agent_activity
from opentlawpy.activities.state_io import load_state_activity, save_state_activity
from opentlawpy.activities.tool_loader import load_tools_activity
from opentlawpy.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    LLM_PROVIDER,
    LOCAL_MODEL_URL,
    OPENROUTER_API_KEY,
)

logger = logging.getLogger(__name__)


def create_activities(*, temporal_client: Client) -> list:
    if LLM_PROVIDER == "anthropic":
        logger.info("Using anthropic client.")
        from opentlawpy.llm.anthropic_client import AnthropicClient

        llm_client = AnthropicClient(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    elif LLM_PROVIDER == "local":
        logger.info("Using local client.")
        from opentlawpy.llm.openai_client import OpenAIClient

        llm_client = OpenAIClient(base_url=LOCAL_MODEL_URL)
    else:
        logger.info("Using OpenRouter client.")
        from opentlawpy.llm.openrouter_client import OpenRouterClient

        llm_client = OpenRouterClient(api_key=OPENROUTER_API_KEY)

    return [
        create_call_llm_activity(llm_client=llm_client),
        create_compact_history_activity(llm_client=llm_client),
        create_poke_agent_activity(temporal_client=temporal_client),
        execute_bash_command,
        read_file_activity,
        write_file_activity,
        load_tools_activity,
        gather_tool_results_activity,
        save_state_activity,
        load_state_activity,
    ]
