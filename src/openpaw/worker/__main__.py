import asyncio
import logging

from temporalio.worker import Worker

from openpaw.activities.create_activities import create_activities
from openpaw.config import TASK_QUEUE, TEMPORAL_ADDRESS
from openpaw.logging import setup_logging
from openpaw.worker.worker import create_temporal_client
from openpaw.workflows.agent_workflow import AgentWorkflow
from openpaw.workflows.heartbeat_workflow import HeartbeatWorkflow
from openpaw.workflows.sub_agent_workflow import SubAgentWorkflow

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> None:
    client = await create_temporal_client(temporal_address=TEMPORAL_ADDRESS)
    logger.info(f"Worker connected to Temporal at {TEMPORAL_ADDRESS}, task queue: {TASK_QUEUE}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
        activities=create_activities(temporal_client=client),
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
