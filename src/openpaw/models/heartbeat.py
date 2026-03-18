from dataclasses import dataclass


@dataclass
class HeartbeatWorkflowInput:
    chat_id: str
    parent_workflow_id: str
    output_activity: str
    output_task_queue: str


@dataclass
class PokeAgentInput:
    chat_id: str
    workflow_id: str
    output_activity: str
    output_task_queue: str
    message: str = ""


@dataclass
class PokeAgentOutput:
    success: bool
