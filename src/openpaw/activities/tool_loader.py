from temporalio import activity

from openpaw.models.tools import ToolDefinition
from openpaw.utils.tool_loader import load_tools


@activity.defn(name="load_tools_activity")
async def load_tools_activity() -> list[ToolDefinition]:
    return load_tools()
