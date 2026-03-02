from dataclasses import dataclass


@dataclass
class IncomingMessage:
    sender: str
    text: str


@dataclass
class SendMessageInput:
    phone_number: str
    text: str


@dataclass
class SendMessageOutput:
    success: bool
    error: str | None = None
