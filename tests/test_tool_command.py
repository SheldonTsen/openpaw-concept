import pytest

from opentlawpy.activities.tool_command import execute_bash_command
from opentlawpy.models.tool_activities import BashCommandOutput


@pytest.fixture(autouse=True)
def _patch_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("opentlawpy.activities.tool_command.WORKSPACE_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_execute_simple_command():
    result = await execute_bash_command(BashCommandOutput(command="echo hello"))
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""


@pytest.mark.asyncio
async def test_execute_command_with_nonzero_exit():
    result = await execute_bash_command(BashCommandOutput(command="ls /nonexistent_path_xyz"))
    assert result.success is False
    assert result.exit_code != 0
    assert result.stderr != ""


@pytest.mark.asyncio
async def test_execute_command_timeout():
    result = await execute_bash_command(BashCommandOutput(command="sleep 10", timeout=1))
    assert result.success is False
    assert result.exit_code == -1
    assert "timed out" in result.stderr
