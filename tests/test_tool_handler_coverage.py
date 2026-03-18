"""Verify every TOOL.md has a matching handler module, and activity references are valid."""

import importlib
import inspect
import pkgutil

import openpaw.activities as _activities_pkg
from openpaw.models.tools import ToolTier
from openpaw.utils.tool_loader import load_tools

# Discover all registered activity names by scanning every module in the activities package
REGISTERED_ACTIVITIES: set[str] = set()

for module_info in pkgutil.iter_modules(_activities_pkg.__path__):
    mod = importlib.import_module(f"openpaw.activities.{module_info.name}")
    for _, obj in inspect.getmembers(mod, inspect.isfunction):
        defn = getattr(obj, "__temporal_activity_definition", None)
        if defn is not None:
            REGISTERED_ACTIVITIES.add(defn.name)


def _load_all_tools():
    """Load all tools (all tiers) so nothing is filtered out."""
    return load_tools(include_tiers=list(ToolTier))


def test_every_tool_has_handler():
    """Every TOOL.md should have a matching openpaw.tool_handlers.<name> module."""
    tools = _load_all_tools()
    assert len(tools) > 0, "No tools loaded — check tools directory"

    for tool in tools:
        mod = importlib.import_module(f"openpaw.tool_handlers.{tool.name}")
        assert hasattr(mod, "handle"), f"Handler module for '{tool.name}' missing handle() function"
        assert callable(mod.handle), f"handle in '{tool.name}' handler is not callable"


def test_all_tools_use_valid_tier():
    """Every TOOL.md must use a tier from the ToolTier enum."""
    tools = _load_all_tools()
    valid_tiers = set(ToolTier)

    for tool in tools:
        tier = tool.metadata.get("tier", "common")
        assert tier in valid_tiers, (
            f"Tool '{tool.name}' has invalid tier '{tier}'. Valid tiers: {sorted(valid_tiers)}"
        )


def test_activity_tools_reference_registered_activities():
    """Tools with type=activity must reference a real registered activity name."""
    tools = _load_all_tools()
    activity_tools = [t for t in tools if t.metadata.get("type") == "activity"]
    assert len(activity_tools) > 0, "Expected at least one activity-type tool"

    for tool in activity_tools:
        activity_name = tool.metadata.get("activity")
        assert activity_name is not None, (
            f"Activity tool '{tool.name}' missing 'activity' key in metadata"
        )
        assert activity_name in REGISTERED_ACTIVITIES, (
            f"Activity tool '{tool.name}' references '{activity_name}' "
            f"but it's not registered. Known: {REGISTERED_ACTIVITIES}"
        )
