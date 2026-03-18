from dataclasses import dataclass


@dataclass
class AgentWorkflowInput:
    chat_id: str
    output_activity: str
    output_task_queue: str
    enable_heartbeat: bool


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
