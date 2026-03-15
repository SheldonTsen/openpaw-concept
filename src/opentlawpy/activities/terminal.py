import logging

from temporalio import activity

from opentlawpy.models.messages import SendMessageInput, SendMessageOutput

logger = logging.getLogger(__name__)


@activity.defn(name="send_terminal_message")
def send_terminal_message(input: SendMessageInput) -> SendMessageOutput:
    logger.info(f"Sending terminal message for session {input.phone_number}")
    print(f"\nAgent: {input.text}\n")
    return SendMessageOutput(text=input.text)
