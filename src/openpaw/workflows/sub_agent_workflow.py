import asyncio
import importlib
import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from openpaw.activities.gather_tool_results import gather_tool_results_activity
    from openpaw.activities.tool_loader import load_tools_activity
    from openpaw.config import (
        LLM_MODEL,
        LLM_TIMEOUT_SECONDS,
        SUB_AGENT_MAX_ITERATIONS,
        SUB_AGENT_SYSTEM_PROMPT,
    )
    from openpaw.models.gather_tool_results import (
        GatherToolResultsInput,
        GatherToolResultsOutput,
    )
    from openpaw.models.llm_call import LLMCallInput, LLMCallOutput
    from openpaw.models.messages import SendMessageInput
    from openpaw.models.sub_agent import SubAgentInput
    from openpaw.models.tools import ToolDefinition

logger = logging.getLogger(__name__)


@workflow.defn
class SubAgentWorkflow:
    def __init__(self) -> None:
        self._conversation_history: list[dict] = []
        self._tool_definitions: list[ToolDefinition] = []
        self._tool_defs_for_llm: list[dict] = []
        self._approval_response: bool | None = None
        self._awaiting_approval: bool = False

    @workflow.run
    async def run(self, input: SubAgentInput) -> str:
        self._input = input
        all_tools = await workflow.execute_activity(
            load_tools_activity,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        self._tool_definitions = [t for t in all_tools if t.name != "delegate_task"]
        self._tool_defs_for_llm = [t.to_llm_format() for t in self._tool_definitions]

        self._conversation_history.append({"role": "user", "content": input.task})

        system_prompt = input.system_prompt or SUB_AGENT_SYSTEM_PROMPT

        await self._thinking_loop(system_prompt=system_prompt)

        return self._conversation_history[-1]["content"]

    @workflow.signal
    def new_message(self, text: str) -> None:
        if self._awaiting_approval:
            self._approval_response = text.strip().upper() == "YES"

    async def _send_status(self, text: str) -> None:
        try:
            await workflow.execute_activity(
                self._input.output_activity,
                arg=SendMessageInput(phone_number=self._input.chat_id, text=text),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),
                task_queue=self._input.output_task_queue,
            )
        except ActivityError as exc:
            workflow.logger.warning(f"Sub-agent failed to send status: {exc}")

    async def _thinking_loop(self, *, system_prompt: str) -> None:
        for _ in range(SUB_AGENT_MAX_ITERATIONS):
            now = workflow.now().strftime("%Y-%m-%d %H:%M %Z")
            tool_docs = "\n\n".join(f"### {t.name}\n{t.body}" for t in self._tool_definitions)
            system_content = (
                f"Current time: {now}\n\n{system_prompt}\n\n## Tool Documentation\n\n{tool_docs}"
            )
            messages = [{"role": "system", "content": system_content}] + self._conversation_history

            llm_output = await workflow.execute_activity(
                "call_llm",
                arg=LLMCallInput(
                    messages=messages,
                    model=LLM_MODEL,
                    tools=self._tool_defs_for_llm,
                ),
                result_type=LLMCallOutput,
                start_to_close_timeout=timedelta(seconds=LLM_TIMEOUT_SECONDS + 30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            if not llm_output.tool_calls:
                workflow.logger.info("Sub-agent: no more tool calls. Exiting loop.")
                self._conversation_history.append(
                    {
                        "role": "assistant",
                        "content": llm_output.response_text,
                    }
                )
                return

            workflow.logger.info("Sub-agent: appending tool_call results to conversation history.")
            self._conversation_history.append(
                {
                    "role": "assistant",
                    "content": llm_output.response_text or "",
                    "tool_calls": llm_output.tool_calls,
                }
            )

            tasks = [self._dispatch(tool_call=tc) for tc in llm_output.tool_calls]
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

        workflow.logger.info(f"Sub-agent: maximum iterations reached: {SUB_AGENT_MAX_ITERATIONS}")
        self._conversation_history.append(
            {
                "role": "assistant",
                "content": (
                    f"Sub-agent reached iteration limit ({SUB_AGENT_MAX_ITERATIONS}). "
                    f"Here is what I have so far: "
                    f"{self._conversation_history[-1].get('content', 'No results yet.')}"
                ),
            }
        )

    async def _dispatch(self, tool_call: dict) -> str:
        """Dispatch a single tool call to its handler via importlib convention."""
        logger.info(f"Sub-agent dispatching tool call for {tool_call}")
        func = tool_call["function"]
        name = func["name"]
        args = func["arguments"]

        try:
            with workflow.unsafe.imports_passed_through():
                mod = importlib.import_module(f"openpaw.tool_handlers.{name}")
        except ModuleNotFoundError:
            return f"Error: Unknown tool '{name}'"

        return await mod.handle(args, workflow_ref=self)
