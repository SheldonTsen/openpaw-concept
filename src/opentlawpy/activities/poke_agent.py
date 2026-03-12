import logging
from typing import Callable

from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy

from opentlawpy.config import TASK_QUEUE
from opentlawpy.models.heartbeat import PokeAgentInput, PokeAgentOutput
from opentlawpy.workflows.agent_workflow import AgentWorkflow

logger = logging.getLogger(__name__)


def create_poke_agent_activity(
    *, temporal_client: Client
) -> Callable[[PokeAgentInput], PokeAgentOutput]:
    """Factory that creates a poke_agent activity bound to a Temporal client.

    Uses atomic start-or-signal to ensure the AgentWorkflow is running
    and receives the heartbeat message.
    """

    @activity.defn(name="poke_agent")
    async def poke_agent(input: PokeAgentInput) -> PokeAgentOutput:
        workflow_id = f"whatsapp-{input.chat_id}"
        logger.info(f"Poking agent workflow {workflow_id}")

        try:
            await temporal_client.start_workflow(
                AgentWorkflow.run,
                arg=input.chat_id,
                id=workflow_id,
                task_queue=TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                start_signal="new_message",
                start_signal_args=["system", input.message],
            )
            return PokeAgentOutput(success=True)
        except Exception:
            logger.exception(f"Failed to poke agent workflow {workflow_id}")
            return PokeAgentOutput(success=False)

    return poke_agent
