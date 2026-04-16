import pytest

from openpaw.activities.bash_command import execute_bash_command
from openpaw.models.bash_command import BashCommandInput


@pytest.fixture(autouse=True)
def _patch_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("openpaw.activities.bash_command.WORKSPACE_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_execute_simple_command():
    result = await execute_bash_command(BashCommandInput(command="echo hello"))
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""


@pytest.mark.asyncio
async def test_execute_command_with_nonzero_exit():
    from temporalio.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        await execute_bash_command(BashCommandInput(command="ls /nonexistent_path_xyz"))


@pytest.mark.asyncio
async def test_execute_command_timeout():
    from temporalio.exceptions import ApplicationError

    with pytest.raises(ApplicationError, match="timed out"):
        await execute_bash_command(BashCommandInput(command="sleep 10", timeout=1))
