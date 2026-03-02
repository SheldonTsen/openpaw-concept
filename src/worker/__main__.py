import asyncio
import logging
import os

from temporalio.worker import Worker

from src.worker.worker import TASK_QUEUE, create_temporal_client
from src.workflows.agent_workflow import AgentWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def main() -> None:
    client = await create_temporal_client(temporal_address=TEMPORAL_ADDRESS)
    logger.info(f"Worker connected to Temporal at {TEMPORAL_ADDRESS}, task queue: {TASK_QUEUE}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AgentWorkflow],
    )
    await worker.run()


asyncio.run(main())
