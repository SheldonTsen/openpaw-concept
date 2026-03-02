import asyncio
import logging

from temporalio.worker import Worker

from opentlawpy.activities.create_activities import create_activities
from opentlawpy.config import TASK_QUEUE, TEMPORAL_ADDRESS
from opentlawpy.logging import setup_logging
from opentlawpy.worker.worker import create_temporal_client
from opentlawpy.workflows.agent_workflow import AgentWorkflow

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> None:
    client = await create_temporal_client(temporal_address=TEMPORAL_ADDRESS)
    logger.info(f"Worker connected to Temporal at {TEMPORAL_ADDRESS}, task queue: {TASK_QUEUE}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AgentWorkflow],
        activities=create_activities(),
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
