from dataclasses import dataclass


@dataclass
class SubAgentInput:
    task: str
    system_prompt: str = ""
