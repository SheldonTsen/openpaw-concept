import asyncio
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from opentlawpy.config import WORKFLOW_TIMEOUT_MINUTES

from opentlawpy.models.messages import IncomingMessage, SendMessageInput


@workflow.defn
class AgentWorkflow:
    def __init__(self) -> None:
        self._pending_messages: list[IncomingMessage] = []

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
        response_text = f"Hello! I received: {message.text}"

        await workflow.execute_activity(
            "send_whatsapp_message",
            arg=SendMessageInput(phone_number=chat_id, text=response_text),
            start_to_close_timeout=timedelta(seconds=30),
        )
