from dataclasses import dataclass, field
from enum import StrEnum


class ToolTier(StrEnum):
    ESSENTIAL = "essential"
    COMMON = "common"
    SPECIALIZED = "specialized"
    EXPERIMENTAL = "experimental"


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    metadata: dict = field(default_factory=dict)
    body: str = ""

    def to_llm_format(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
