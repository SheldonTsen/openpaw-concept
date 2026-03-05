import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from opentlawpy.activities.tool_loader import load_tools_activity
    from opentlawpy.config import (
        LLM_MODEL,
        MAX_TOOL_ITERATIONS,
        SYSTEM_PROMPT,
        WHATSAPP_TASK_QUEUE,
        WORKFLOW_TIMEOUT_MINUTES,
    )
    from opentlawpy.models.llm import LLMCallInput, LLMCallOutput
    from opentlawpy.workflows.tool_executor import execute_tool_calls

from opentlawpy.models.messages import IncomingMessage, SendMessageInput


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

                self._conversation_history.append(
                    {"role": "user", "content": message.text}
                )

                try:
                    await self._thinking_loop()
                except ActivityError as exc:
                    workflow.logger.error(f"Activity failed for {chat_id}: {exc}")
                    self._conversation_history.append(
                        {
                            "role": "assistant",
                            "content": (
                                "Sorry, I'm having trouble processing your message "
                                "right now. Please try again in a moment."
                            ),
                        }
                    )

                response_text = self._conversation_history[-1]["content"]

                await workflow.execute_activity(
                    "send_whatsapp_message",
                    arg=SendMessageInput(
                        phone_number=chat_id, text=response_text
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                    task_queue=WHATSAPP_TASK_QUEUE,
                )

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
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            if not llm_output.tool_calls:
                self._conversation_history.append(
                    {
                        "role": "assistant",
                        "content": llm_output.response_text,
                    }
                )
                # no more tools to call - exit function
                return

            self._conversation_history.append(
                {
                    "role": "assistant",
                    # openai expects content to be empty for tool calls
                    "content": llm_output.response_text or "",
                    "tool_calls": llm_output.tool_calls,
                }
            )

            tool_results = await execute_tool_calls(
                tool_calls=llm_output.tool_calls,
            )
            self._conversation_history.extend(tool_results)

        # Hit max iterations
        self._conversation_history.append(
            {
                "role": "assistant",
                "content": (
                    f"I've reached my thinking limit for this message "
                    f"({MAX_TOOL_ITERATIONS} iterations)."
                ),
            }
        )
