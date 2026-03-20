import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

from openpaw.config import SUB_AGENT_TIMEOUT_MINUTES
from openpaw.models.sub_agent import SubAgentInput
from openpaw.workflows.sub_agent_workflow import SubAgentWorkflow

logger = logging.getLogger(__name__)


async def handle(args: dict, *, workflow_ref=None, **kwargs) -> str:
    logger.info(f"Delegating task to sub-agent: {args['task'][:100]}")

    sub_input = SubAgentInput(
        task=args["task"],
        output_activity=workflow_ref._input.output_activity,
        output_task_queue=workflow_ref._input.output_task_queue,
        chat_id=workflow_ref._input.chat_id,
    )

    child_id = f"sub-{workflow.info().workflow_id}-{workflow.uuid4().hex[:8]}"
    workflow_ref._active_child_id = child_id

    try:
        result = await workflow.execute_child_workflow(
            SubAgentWorkflow.run,
            arg=sub_input,
            id=child_id,
            parent_close_policy=ParentClosePolicy.TERMINATE,
            execution_timeout=timedelta(minutes=SUB_AGENT_TIMEOUT_MINUTES),
        )
        return result
    except Exception as exc:
        logger.error(f"Sub-agent failed: {exc}")
        return f"Error: Sub-agent failed — {exc}"
    finally:
        workflow_ref._active_child_id = None
