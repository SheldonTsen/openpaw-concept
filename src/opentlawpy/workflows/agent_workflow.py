import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from opentlawpy.config import LLM_MODEL, WHATSAPP_TASK_QUEUE, WORKFLOW_TIMEOUT_MINUTES
    from opentlawpy.models.llm import LLMCallInput, LLMCallOutput

from opentlawpy.models.messages import IncomingMessage, SendMessageInput


@workflow.defn
class AgentWorkflow:
    def __init__(self) -> None:
        self._pending_messages: list[IncomingMessage] = []
        self._conversation_history: list[dict] = []

    @workflow.run
    async def run(self, chat_id: str) -> None:
        while True:
            try:
                await workflow.wait_condition(
                    lambda: len(self._pending_messages) > 0,
                    timeout=timedelta(minutes=WORKFLOW_TIMEOUT_MINUTES),
                )
            except asyncio.TimeoutError:
                workflow.logger.info(
                    f"Workflow {chat_id} timed out after "
                    f"{WORKFLOW_TIMEOUT_MINUTES} minutes of inactivity"
                )
                return

            # Process all pending messages
            while self._pending_messages:
                message = self._pending_messages.pop(0)
                await self._handle_message(chat_id=chat_id, message=message)

    @workflow.signal
    def new_message(self, sender: str, text: str) -> None:
        self._pending_messages.append(IncomingMessage(sender=sender, text=text))

    async def _handle_message(self, chat_id: str, message: IncomingMessage) -> None:
        self._conversation_history.append({"role": "user", "content": message.text})

        llm_output = await workflow.execute_activity(
            "call_llm",
            arg=LLMCallInput(
                messages=list(self._conversation_history),
                model=LLM_MODEL,
            ),
            result_type=LLMCallOutput,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        response_text = llm_output.response_text
        self._conversation_history.append({"role": "assistant", "content": response_text})

        await workflow.execute_activity(
            "send_whatsapp_message",
            arg=SendMessageInput(phone_number=chat_id, text=response_text),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue=WHATSAPP_TASK_QUEUE,
        )
