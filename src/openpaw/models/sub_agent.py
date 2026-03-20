from dataclasses import dataclass


@dataclass
class SubAgentInput:
    task: str
    output_activity: str
    output_task_queue: str
    chat_id: str
    system_prompt: str = ""
