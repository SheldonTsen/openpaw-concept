from dataclasses import dataclass, field


@dataclass
class SaveStateInput:
    chat_id: str
    conversation_history: list[dict] = field(default_factory=list)


@dataclass
class SaveStateOutput:
    success: bool


@dataclass
class LoadStateInput:
    chat_id: str


@dataclass
class LoadStateOutput:
    conversation_history: list[dict] = field(default_factory=list)
    found: bool = False
