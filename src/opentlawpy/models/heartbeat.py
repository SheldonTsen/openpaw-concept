from dataclasses import dataclass


@dataclass
class PokeAgentInput:
    chat_id: str
    message: str = ""


@dataclass
class PokeAgentOutput:
    success: bool
