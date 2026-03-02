import asyncio
import logging
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor

from neonize.client import NewClient
from neonize.utils import log as neonize_log
from temporalio.worker import Worker

from opentlawpy.activities.whatsapp import create_send_whatsapp_message_activity
from opentlawpy.config import MY_WHATSAPP_NUMBER, NEONIZE_DB_PATH, TASK_QUEUE, TEMPORAL_ADDRESS
from opentlawpy.logging import setup_logging
from opentlawpy.whatsapp.listener import WhatsAppListener
from opentlawpy.worker.worker import create_temporal_client

setup_logging()
logger = logging.getLogger(__name__)
neonize_log.setLevel(logging.INFO)


def force_exit(*_):
    """Force exit — neonize's Go runtime swallows signals."""
    logger.info("Shutting down...")
    os._exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, force_exit)
    signal.signal(signal.SIGTERM, force_exit)

    if not MY_WHATSAPP_NUMBER:
        logger.error("MY_WHATSAPP_NUMBER environment variable is required")
        return

    logger.info(f"Temporal address: {TEMPORAL_ADDRESS}")
    logger.info(f"WhatsApp number: {MY_WHATSAPP_NUMBER}")
    logger.info(f"Neonize DB: {NEONIZE_DB_PATH}")

    # Create neonize client
    neonize_client = NewClient(NEONIZE_DB_PATH)

    # Create send activity bound to neonize client
    send_activity = create_send_whatsapp_message_activity(neonize_client=neonize_client)

    # Shared state for cross-thread access
    state: dict = {}
    loop = asyncio.new_event_loop()
    worker_ready = threading.Event()

    def run_activity_worker():
        """Run send-activity-only Temporal worker on a daemon thread."""
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            _start_activity_worker(
                state=state,
                send_activity=send_activity,
                worker_ready=worker_ready,
            )
        )

    daemon = threading.Thread(target=run_activity_worker, daemon=True, name="activity-worker")
    daemon.start()

    # Wait for Temporal connection
    logger.info("Waiting for Temporal connection...")
    worker_ready.wait(timeout=30)
    if not worker_ready.is_set():
        logger.error("Temporal connection failed within 30 seconds")
        return
    logger.info("Activity worker ready")

    # Start WhatsApp listener on main thread (blocks)
    listener = WhatsAppListener(
        neonize_client=neonize_client,
        temporal_client=state["temporal_client"],
        my_whatsapp_number=MY_WHATSAPP_NUMBER,
        event_loop=loop,
    )
    listener.start()


async def _start_activity_worker(
    state: dict,
    send_activity,
    worker_ready: threading.Event,
) -> None:
    """Connect to Temporal and run the send-activity-only worker."""
    temporal_client = await create_temporal_client(temporal_address=TEMPORAL_ADDRESS)
    state["temporal_client"] = temporal_client

    logger.info(f"Connected to Temporal at {TEMPORAL_ADDRESS}, task queue: {TASK_QUEUE}")
    worker_ready.set()

    worker = Worker(
        temporal_client,
        task_queue=TASK_QUEUE,
        activities=[send_activity],
        activity_executor=ThreadPoolExecutor(max_workers=5),
    )
    await worker.run()


main()
