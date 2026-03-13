from dataclasses import dataclass


@dataclass
class IncomingMessage:
    text: str


@dataclass
class SendMessageInput:
    phone_number: str
    text: str


@dataclass
class SendMessageOutput:
    text: str
