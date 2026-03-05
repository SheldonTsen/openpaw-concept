import pytest

from opentlawpy.activities.file_operations import read_file_activity, write_file_activity
from opentlawpy.models.tool_activities import ReadFileInput, WriteFileInput


@pytest.fixture(autouse=True)
def _patch_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("opentlawpy.activities.file_operations.WORKSPACE_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_read_existing_file(tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world")

    result = await read_file_activity(ReadFileInput(path="hello.txt"))
    assert result.success is True
    assert result.content == "hello world"
    assert result.error is None


@pytest.mark.asyncio
async def test_read_nonexistent_file():
    result = await read_file_activity(ReadFileInput(path="does_not_exist.txt"))
    assert result.success is False
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_read_file_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr("opentlawpy.activities.file_operations.MAX_READ_BYTES", 100)

    test_file = tmp_path / "big.txt"
    test_file.write_text("x" * 200)

    result = await read_file_activity(ReadFileInput(path="big.txt"))
    assert result.success is False
    assert "too large" in result.error.lower()


@pytest.mark.asyncio
async def test_read_file_path_traversal():
    result = await read_file_activity(ReadFileInput(path="../../../etc/passwd"))
    assert result.success is False
    assert "traversal" in result.error.lower()


@pytest.mark.asyncio
async def test_write_new_file(tmp_path):
    result = await write_file_activity(WriteFileInput(path="new.txt", content="hello"))
    assert result.success is True
    assert result.bytes_written == 5

    written = (tmp_path / "new.txt").read_text()
    assert written == "hello"


@pytest.mark.asyncio
async def test_write_file_append_mode(tmp_path):
    test_file = tmp_path / "append.txt"
    test_file.write_text("first ")

    result = await write_file_activity(
        WriteFileInput(path="append.txt", content="second", mode="append")
    )
    assert result.success is True

    content = test_file.read_text()
    assert content == "first second"


@pytest.mark.asyncio
async def test_write_file_creates_directories(tmp_path):
    result = await write_file_activity(
        WriteFileInput(path="subdir/nested/file.txt", content="deep")
    )
    assert result.success is True

    written = (tmp_path / "subdir" / "nested" / "file.txt").read_text()
    assert written == "deep"


@pytest.mark.asyncio
async def test_write_file_path_traversal():
    result = await write_file_activity(WriteFileInput(path="../../../tmp/evil.txt", content="bad"))
    assert result.success is False
    assert "traversal" in result.error.lower()
