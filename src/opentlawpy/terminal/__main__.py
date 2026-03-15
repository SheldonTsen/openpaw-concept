import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from temporalio.common import WorkflowIDConflictPolicy
from temporalio.worker import Worker

from opentlawpy.activities.terminal import send_terminal_message
from opentlawpy.config import TASK_QUEUE, TEMPORAL_ADDRESS, TERMINAL_TASK_QUEUE
from opentlawpy.logging import setup_logging
from opentlawpy.models.messages import AgentWorkflowInput
from opentlawpy.worker.worker import create_temporal_client
from opentlawpy.workflows.agent_workflow import AgentWorkflow

setup_logging()
logger = logging.getLogger(__name__)


async def _async_main() -> None:
    logger.info(f"Connecting to Temporal at {TEMPORAL_ADDRESS}...")
    client = await create_temporal_client(temporal_address=TEMPORAL_ADDRESS)
    logger.info("Connected to Temporal")

    session_id = uuid.uuid4().hex[:8]
    workflow_id = f"terminal-{session_id}"

    worker = Worker(
        client,
        task_queue=TERMINAL_TASK_QUEUE,
        activities=[send_terminal_message],
        activity_executor=ThreadPoolExecutor(max_workers=2),
    )

    async with worker:
        print(f"Terminal session: {session_id}")
        print(f"Workflow ID: {workflow_id}")
        print("Type your message and press Enter. Ctrl+C to quit.\n")

        loop = asyncio.get_event_loop()

        try:
            while True:
                try:
                    text = await loop.run_in_executor(None, input, "You: ")
                except EOFError:
                    break

                text = text.strip()
                if not text:
                    continue

                await client.start_workflow(
                    AgentWorkflow.run,
                    arg=AgentWorkflowInput(
                        chat_id=session_id,
                        output_activity="send_terminal_message",
                        output_task_queue=TERMINAL_TASK_QUEUE,
                    ),
                    id=workflow_id,
                    task_queue=TASK_QUEUE,
                    id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                    start_signal="new_message",
                    start_signal_args=[text],
                )
        except KeyboardInterrupt:
            print("\nGoodbye!")


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
