from dataclasses import dataclass


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
