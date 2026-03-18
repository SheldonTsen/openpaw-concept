from dataclasses import dataclass


@dataclass
class BashCommandInput:
    command: str
    timeout: int = 30


@dataclass
class BashCommandOutput:
    stdout: str
    stderr: str
    exit_code: int
    success: bool
