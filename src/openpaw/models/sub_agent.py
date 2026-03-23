from dataclasses import dataclass, field


@dataclass
class SubAgentInput:
    task: str
    output_activity: str
    output_task_queue: str
    chat_id: str
    system_prompt: str = ""
    initial_conversation_history: list[dict] = field(default_factory=list)
    send_final_response: bool = False
