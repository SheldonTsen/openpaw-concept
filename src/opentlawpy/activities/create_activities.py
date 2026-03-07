from opentlawpy.activities.file_operations import read_file_activity, write_file_activity
from opentlawpy.activities.llm_call import create_call_llm_activity
from opentlawpy.activities.gather_tool_results import gather_tool_results_activity
from opentlawpy.activities.bash_command import execute_bash_command
from opentlawpy.activities.tool_loader import load_tools_activity
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
        execute_bash_command,
        read_file_activity,
        write_file_activity,
        load_tools_activity,
        gather_tool_results_activity,
    ]
