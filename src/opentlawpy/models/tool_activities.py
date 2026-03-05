from dataclasses import dataclass


@dataclass
class BashCommandOutput:
    command: str
    timeout: int = 30


@dataclass
class ToolCommandOutput:
    stdout: str
    stderr: str
    exit_code: int
    success: bool


@dataclass
class ReadFileInput:
    path: str
    encoding: str = "utf-8"


@dataclass
class ReadFileOutput:
    content: str
    success: bool
    error: str | None = None


@dataclass
class WriteFileInput:
    path: str
    content: str
    mode: str = "overwrite"


@dataclass
class WriteFileOutput:
    success: bool
    bytes_written: int = 0
    error: str | None = None
