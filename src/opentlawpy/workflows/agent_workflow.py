import asyncio
import importlib
import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from opentlawpy.activities.gather_tool_results import gather_tool_results_activity
    from opentlawpy.activities.state_io import load_state_activity, save_state_activity
    from opentlawpy.activities.tool_loader import load_tools_activity
    from opentlawpy.config import (
        LLM_MODEL,
        MAX_TOOL_ITERATIONS,
        SYSTEM_PROMPT,
        WHATSAPP_TASK_QUEUE,
        WORKFLOW_TIMEOUT_MINUTES,
    )
    from opentlawpy.models.llm import LLMCallInput, LLMCallOutput
    from opentlawpy.models.state import LoadStateInput, SaveStateInput
    from opentlawpy.models.tool_activities import GatherToolResultsInput, GatherToolResultsOutput

from opentlawpy.models.messages import IncomingMessage, SendMessageInput

logger = logging.getLogger(__name__)


@workflow.defn
class AgentWorkflow:
    def __init__(self) -> None:
        self._pending_messages: list[IncomingMessage] = []
        self._conversation_history: list[dict] = []
        self._tool_defs_for_llm: list[dict] = []

    @workflow.run
    async def run(self, chat_id: str) -> None:
        tools = await workflow.execute_activity(
            load_tools_activity,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        self._tool_defs_for_llm = [t.to_llm_format() for t in tools]

        load_output = await workflow.execute_activity(
            load_state_activity,
            arg=LoadStateInput(chat_id=chat_id),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        if load_output.found:
            self._conversation_history = load_output.conversation_history
            workflow.logger.info(
                f"Restored {len(self._conversation_history)} messages for {chat_id}"
            )

        while True:
            try:
                await workflow.wait_condition(
                    lambda: len(self._pending_messages) > 0,
                    timeout=timedelta(minutes=WORKFLOW_TIMEOUT_MINUTES),
                )
            except asyncio.TimeoutError:
                workflow.logger.info(
                    f"Workflow {chat_id} timed out after "
                    f"{WORKFLOW_TIMEOUT_MINUTES} minutes of inactivity"
                )
                return

            while self._pending_messages:
                message = self._pending_messages.pop(0)

                self._conversation_history.append({"role": "user", "content": message.text})

                # try..except so that the workflow does not fail
                # and still sends an error message to the user
                # otherwise the user never gets a response back
                try:
                    await self._thinking_loop()
                except ActivityError as exc:
                    workflow.logger.error(f"Activity failed for {chat_id}: {exc}")
                    self._conversation_history.append(
                        {
                            "role": "assistant",
                            "content": (
                                "Sorry, I'm having trouble processing your message "
                                "right now. Please try again in a moment. This is likely "
                                "an internal error."
                            ),
                        }
                    )

                response_text = self._conversation_history[-1]["content"]

                try:
                    await workflow.execute_activity(
                        "send_whatsapp_message",
                        arg=SendMessageInput(phone_number=chat_id, text=response_text),
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                        task_queue=WHATSAPP_TASK_QUEUE,
                    )
                except ActivityError as exc:
                    workflow.logger.error(f"Failed to send WhatsApp message for {chat_id}: {exc}")

                try:
                    await workflow.execute_activity(
                        save_state_activity,
                        arg=SaveStateInput(
                            chat_id=chat_id,
                            conversation_history=self._conversation_history,
                        ),
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )
                except ActivityError as exc:
                    workflow.logger.error(f"Failed to save state for {chat_id}: {exc}")

    @workflow.signal
    def new_message(self, sender: str, text: str) -> None:
        self._pending_messages.append(IncomingMessage(sender=sender, text=text))

    async def _thinking_loop(self) -> None:
        for _ in range(MAX_TOOL_ITERATIONS):
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._conversation_history

            llm_output = await workflow.execute_activity(
                "call_llm",
                arg=LLMCallInput(
                    messages=messages,
                    model=LLM_MODEL,
                    tools=self._tool_defs_for_llm,
                ),
                result_type=LLMCallOutput,
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            if not llm_output.tool_calls:
                workflow.logger.info(f"No more tool calls. Exiting loop.")
                self._conversation_history.append(
                    {
                        "role": "assistant",
                        "content": llm_output.response_text,
                    }
                )
                # no more tools to call - exit function
                return

            workflow.logger.info(f"Appending tool_call results to conversation history.")
            self._conversation_history.append(
                {
                    "role": "assistant",
                    # openai expects content to be empty for tool calls
                    "content": llm_output.response_text or "",
                    "tool_calls": llm_output.tool_calls,
                }
            )

            # execute tool calls in parallel
            workflow.logger.info(f"Calling execute_tool_calls with: {llm_output.tool_calls}")
            tasks = [_dispatch(tool_call=tc) for tc in llm_output.tool_calls]
            tool_results = await asyncio.gather(*tasks, return_exceptions=True)

            gather_tool_results_output: GatherToolResultsOutput = await workflow.execute_activity(
                gather_tool_results_activity,
                arg=GatherToolResultsInput(
                    tool_calls=llm_output.tool_calls, tool_results=tool_results
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            self._conversation_history.extend(gather_tool_results_output.tool_results_as_messages)

        # Hit max iterations
        workflow.logger.info(f"Maximum tool calls reached.")
        self._conversation_history.append(
            {
                "role": "assistant",
                "content": (
                    f"I've reached my thinking limit for this message "
                    f"({MAX_TOOL_ITERATIONS} iterations)."
                ),
            }
        )


async def _dispatch(tool_call: dict) -> str:
    """Dispatch a single tool call to its handler via importlib convention.

    Tool name "bash" → opentlawpy.tool_handlers.bash → handle(args).
    """
    logger.info(f"Dispatching tool call for {tool_call}")
    func = tool_call["function"]
    name = func["name"]
    args = func["arguments"]

    try:
        with workflow.unsafe.imports_passed_through():
            mod = importlib.import_module(f"opentlawpy.tool_handlers.{name}")
    except ModuleNotFoundError:
        return f"Error: Unknown tool '{name}'"

    return await mod.handle(args)
