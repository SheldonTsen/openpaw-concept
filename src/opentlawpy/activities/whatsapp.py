from typing import Callable

from temporalio import activity

from opentlawpy.models.messages import SendMessageInput, SendMessageOutput


def create_send_whatsapp_message_activity(
    neonize_client,
) -> Callable[[SendMessageInput], SendMessageOutput]:
    """Factory that creates a send_whatsapp_message activity bound to a neonize client.

    The returned function is sync (neonize's send_message is a Go FFI call).
    Temporal runs it on a thread pool automatically.
    """
    from neonize.utils import build_jid

    @activity.defn(name="send_whatsapp_message")
    def send_whatsapp_message(input: SendMessageInput) -> SendMessageOutput:
        jid = build_jid(input.phone_number)
        neonize_client.send_message(jid, input.text)
        return SendMessageOutput(text=input.text)

    return send_whatsapp_message
