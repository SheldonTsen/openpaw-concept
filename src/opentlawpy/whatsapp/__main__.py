import asyncio
import logging
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor

from neonize.client import NewClient
from neonize.utils import log as neonize_log
from temporalio.client import Client
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


async def _run_activity_worker(client: Client, send_activity) -> None:
    """Run the send-activity-only Temporal worker forever."""
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        activities=[send_activity],
        activity_executor=ThreadPoolExecutor(max_workers=5),
    )
    await worker.run()


def main() -> None:
    signal.signal(signal.SIGINT, force_exit)
    signal.signal(signal.SIGTERM, force_exit)

    if not MY_WHATSAPP_NUMBER:
        logger.error("MY_WHATSAPP_NUMBER environment variable is required")
        return

    logger.info(f"Temporal address: {TEMPORAL_ADDRESS}")
    logger.info(f"WhatsApp number: {MY_WHATSAPP_NUMBER}")
    logger.info(f"Neonize DB: {NEONIZE_DB_PATH}")

    neonize_client = NewClient(NEONIZE_DB_PATH)
    send_activity = create_send_whatsapp_message_activity(neonize_client=neonize_client)

    # Start event loop in daemon thread
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True, name="async-loop").start()

    # Connect to Temporal (blocks until connected)
    logger.info("Connecting to Temporal...")
    temporal_client = asyncio.run_coroutine_threadsafe(
        create_temporal_client(temporal_address=TEMPORAL_ADDRESS),
        loop,
    ).result(timeout=30)
    logger.info(f"Connected to Temporal at {TEMPORAL_ADDRESS}, task queue: {TASK_QUEUE}")

    # Start activity worker (non-blocking — runs on the loop)
    worker_future = asyncio.run_coroutine_threadsafe(
        _run_activity_worker(client=temporal_client, send_activity=send_activity),
        loop,
    )
    worker_future.add_done_callback(
        lambda f: logger.error(f"Activity worker died: {f.exception()}") if f.exception() else None
    )

    # Start WhatsApp listener on main thread (blocks)
    listener = WhatsAppListener(
        neonize_client=neonize_client,
        temporal_client=temporal_client,
        my_whatsapp_number=MY_WHATSAPP_NUMBER,
        event_loop=loop,
    )
    listener.start()


if __name__ == "__main__":
    main()
