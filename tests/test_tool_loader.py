from opentlawpy.utils.tool_loader import load_tools

EXPECTED_ALL_TOOLS = {
    "bash",
    "read_file",
    "write_file",
    "python",
    "web_search",
    "git",
    "grep",
    "calculator",
    "delegate_task",
}

EXPECTED_ESSENTIAL_TOOLS = {"bash", "python", "delegate_task"}


def test_load_all_tools():
    tools = load_tools(include_tiers=["essential", "common", "experimental", "specialized"])
    names = {t.name for t in tools}
    assert names == EXPECTED_ALL_TOOLS


def test_tool_has_required_fields():
    tools = load_tools()
    for tool in tools:
        assert tool.name, "name must not be empty"
        assert tool.description, "description must not be empty"
        assert isinstance(tool.parameters, dict), "parameters must be a dict"
        assert "type" in tool.parameters, "parameters must have a 'type' key"
        assert "properties" in tool.parameters, "parameters must have a 'properties' key"


def test_filter_by_tier():
    tools = load_tools(include_tiers=["essential"])
    names = {t.name for t in tools}
    assert names == EXPECTED_ESSENTIAL_TOOLS


def test_sorted_by_priority():
    tools = load_tools()
    priorities = [t.metadata["priority"] for t in tools]
    assert priorities == sorted(priorities)


def test_to_llm_format():
    tools = load_tools()
    tool = tools[0]
    fmt = tool.to_llm_format()

    assert fmt["type"] == "function"
    assert "function" in fmt
    func = fmt["function"]
    assert func["name"] == tool.name
    assert func["description"] == tool.description
    assert func["parameters"] == tool.parameters
    assert "metadata" not in func


def test_body_populated_from_markdown():
    tools = load_tools()
    for tool in tools:
        assert tool.body, f"{tool.name} TOOL.md should have a markdown body"
        llm_func = tool.to_llm_format()["function"]
        assert "body" not in llm_func, "body should not leak into LLM tool schema"
