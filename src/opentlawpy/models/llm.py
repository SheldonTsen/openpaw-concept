from dataclasses import dataclass


@dataclass
class LLMCallInput:
    messages: list[dict]
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096


@dataclass
class LLMCallOutput:
    response_text: str
    model_used: str
    input_tokens: int
    output_tokens: int
