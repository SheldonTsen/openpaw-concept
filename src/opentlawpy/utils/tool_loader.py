import glob
import os

import yaml

from opentlawpy.config import DEFAULT_TOOL_PRIORITY, TOOLS_DIR
from opentlawpy.models.tools import ToolDefinition

DEFAULT_TIERS = ["essential", "common"]


def _parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a TOOL.md file."""
    parts = text.split("---", maxsplit=2)
    if len(parts) < 3:
        msg = "TOOL.md missing YAML frontmatter (expected --- delimiters)"
        raise ValueError(msg)
    return yaml.safe_load(parts[1])


def load_tools(
    *,
    tools_dir: str = TOOLS_DIR,
    include_tiers: list[str] | None = None,
) -> list[ToolDefinition]:
    """Load tool definitions from TOOL.md files.

    Args:
        tools_dir: Directory containing tool subdirectories with TOOL.md files.
        include_tiers: Filter to only these tiers. Defaults to ["essential", "common"].

    Returns:
        List of ToolDefinition sorted by metadata priority.
    """
    if include_tiers is None:
        include_tiers = DEFAULT_TIERS

    pattern = os.path.join(tools_dir, "*", "TOOL.md")
    tool_files = glob.glob(pattern)

    tools = []
    for tool_file in tool_files:
        with open(tool_file) as f:
            content = f.read()

        frontmatter = _parse_frontmatter(content)

        metadata = frontmatter.get("metadata", {})
        tier = metadata.get("tier", "common")

        if tier not in include_tiers:
            continue

        tools.append(
            ToolDefinition(
                name=frontmatter["name"],
                description=frontmatter["description"],
                parameters=frontmatter["parameters"],
                metadata=metadata,
            )
        )

    tools.sort(key=lambda t: t.metadata.get("priority", DEFAULT_TOOL_PRIORITY))
    return tools
