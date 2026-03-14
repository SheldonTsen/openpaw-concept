import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

from opentlawpy.config import SUB_AGENT_TIMEOUT_MINUTES
from opentlawpy.models.sub_agent import SubAgentInput
from opentlawpy.workflows.sub_agent_workflow import SubAgentWorkflow

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    logger.info(f"Delegating task to sub-agent: {args['task'][:100]}")
    try:
        result = await workflow.execute_child_workflow(
            SubAgentWorkflow.run,
            arg=SubAgentInput(task=args["task"]),
            id=f"sub-{workflow.info().workflow_id}-{workflow.uuid4().hex[:8]}",
            parent_close_policy=ParentClosePolicy.TERMINATE,
            execution_timeout=timedelta(minutes=SUB_AGENT_TIMEOUT_MINUTES),
        )
        return result
    except Exception as exc:
        logger.error(f"Sub-agent failed: {exc}")
        return f"Error: Sub-agent failed — {exc}"
