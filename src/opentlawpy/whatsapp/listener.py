import asyncio
import logging
import time

from neonize.client import NewClient
from neonize.events import ConnectedEv, MessageEv, PairStatusEv
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy

from opentlawpy.config import TASK_QUEUE, WHATSAPP_TASK_QUEUE
from opentlawpy.models.messages import AgentWorkflowInput
from opentlawpy.workflows.agent_workflow import AgentWorkflow

logger = logging.getLogger(__name__)


class WhatsAppListener:
    """Listens for WhatsApp messages via neonize and routes them to Temporal workflows."""

    def __init__(
        self,
        neonize_client: NewClient,
        temporal_client: Client,
        my_whatsapp_number: str,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._neonize_client = neonize_client
        self._temporal_client = temporal_client
        self._my_whatsapp_number = my_whatsapp_number
        self._event_loop = event_loop
        self._start_time = time.time()
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self._neonize_client.event(ConnectedEv)
        def on_connected(_client: NewClient, _event: ConnectedEv):
            logger.info("WhatsApp connected")

        @self._neonize_client.event(PairStatusEv)
        def on_pair_status(_client: NewClient, event: PairStatusEv):
            logger.info(f"Paired as {event.ID.User}")

        @self._neonize_client.event(MessageEv)
        def on_message(_client: NewClient, message: MessageEv):
            self._on_message(message=message)

    def _on_message(self, message: MessageEv) -> None:
        """Handle incoming WhatsApp message (called from neonize's Go thread)."""
        # Filter old messages from WhatsApp's offline queue
        msg_time = message.Info.Timestamp
        if msg_time < self._start_time:
            logger.info(f"Skipping old message (timestamp={msg_time})")
            return

        text = message.Message.conversation or message.Message.extendedTextMessage.text
        if not text:
            logger.info("Skipping message with no text content")
            return

        is_from_me = message.Info.MessageSource.IsFromMe
        sender = message.Info.MessageSource.Sender.User
        chat = message.Info.MessageSource.Chat.User

        # Only process messages I send to myself
        if not is_from_me or chat != self._my_whatsapp_number:
            return

        logger.info(f"Received message from {sender}: {text}")

        # Dispatch to Temporal on the async event loop
        asyncio.run_coroutine_threadsafe(
            self._route_message(sender=sender, text=text),
            self._event_loop,
        )

    async def _route_message(self, sender: str, text: str) -> None:
        """Start-or-signal a Temporal workflow for this chat."""
        workflow_id = f"whatsapp-{sender}"

        try:
            await self._temporal_client.start_workflow(
                AgentWorkflow.run,
                arg=AgentWorkflowInput(
                    chat_id=sender,
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=True,
                ),
                id=workflow_id,
                task_queue=TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                start_signal="new_message",
                start_signal_args=[text],
            )
            logger.info(f"Routed message to workflow {workflow_id}")
        except Exception:
            logger.exception(f"Failed to route message to workflow {workflow_id}")

    def start(self) -> None:
        """Start the neonize client (blocks the calling thread)."""
        logger.info("Starting WhatsApp listener...")
        self._neonize_client.connect()
