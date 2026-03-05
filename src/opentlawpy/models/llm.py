from dataclasses import dataclass, field


@dataclass
class LLMCallInput:
    messages: list[dict]
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096
    tools: list[dict] | None = None


@dataclass
class LLMCallOutput:
    response_text: str
    model_used: str
    input_tokens: int
    output_tokens: int
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: str | None = None
