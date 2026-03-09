from dataclasses import dataclass, field


@dataclass
class CompactHistoryInput:
    conversation_history: list[dict] = field(default_factory=list)
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 2048


@dataclass
class CompactHistoryOutput:
    compacted_history: list[dict] = field(default_factory=list)
    original_message_count: int = 0
    compacted_message_count: int = 0
