import asyncio
import importlib
import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ActivityError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from openpaw.activities.gather_tool_results import gather_tool_results_activity
    from openpaw.activities.state_io import load_state_activity, save_state_activity
    from openpaw.activities.tool_loader import load_tools_activity
    from openpaw.config import (
        COMPACTION_THRESHOLD,
        LLM_MODEL,
        LLM_TIMEOUT_SECONDS,
        MAX_TOOL_ITERATIONS,
        SYSTEM_PROMPT,
        WORKFLOW_TIMEOUT_MINUTES,
    )
    from openpaw.models.compaction import CompactHistoryInput, CompactHistoryOutput
    from openpaw.models.gather_tool_results import (
        GatherToolResultsInput,
        GatherToolResultsOutput,
    )
    from openpaw.models.heartbeat import HeartbeatWorkflowInput
    from openpaw.models.llm_call import LLMCallInput, LLMCallOutput
    from openpaw.models.state_io import LoadStateInput, SaveStateInput
    from openpaw.models.tools import ToolDefinition
    from openpaw.workflows.heartbeat_workflow import HeartbeatWorkflow

from openpaw.models.messages import AgentWorkflowInput, IncomingMessage, SendMessageInput

logger = logging.getLogger(__name__)


@workflow.defn
class AgentWorkflow:
    def __init__(self) -> None:
        self._pending_messages: list[IncomingMessage] = []
        self._conversation_history: list[dict] = []
        self._tool_definitions: list[ToolDefinition] = []
        self._tool_defs_for_llm: list[dict] = []
        self._approval_response: bool | None = None
        self._awaiting_approval: bool = False
        self._active_child_id: str | None = None

    @workflow.run
    async def run(self, input: AgentWorkflowInput) -> None:
        self._input = input
        chat_id = input.chat_id
        wf_id = workflow.info().workflow_id
        if input.enable_heartbeat:
            try:
                await workflow.start_child_workflow(
                    HeartbeatWorkflow.run,
                    arg=HeartbeatWorkflowInput(
                        chat_id=chat_id,
                        parent_workflow_id=wf_id,
                        output_activity=input.output_activity,
                        output_task_queue=input.output_task_queue,
                    ),
                    id=f"heartbeat-{wf_id}",
                    parent_close_policy=ParentClosePolicy.ABANDON,
                    id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                )
            except Exception:
                workflow.logger.info(f"Heartbeat already running for {chat_id}")

        self._tool_definitions = await workflow.execute_activity(
            load_tools_activity,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        self._tool_defs_for_llm = [t.to_llm_format() for t in self._tool_definitions]

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

                await self._send_status(response_text)

                try:
                    await self._maybe_compact_history(chat_id=chat_id)
                except ActivityError as exc:
                    workflow.logger.error(f"Compaction failed for {chat_id}: {exc}")

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
    async def new_message(self, text: str) -> None:
        normalized = text.strip().upper()
        is_approval_answer = normalized in ("YES", "NO")

        if self._awaiting_approval and is_approval_answer:
            self._approval_response = (normalized == "YES")
        elif self._active_child_id and is_approval_answer:
            child_handle = workflow.get_external_workflow_handle(self._active_child_id)
            await child_handle.signal("new_message", text)
        elif self._awaiting_approval or self._active_child_id:
            await self._send_status("Please reply yes or no (case insensitive).")
        else:
            self._pending_messages.append(IncomingMessage(text=text))

    async def _maybe_compact_history(self, *, chat_id: str) -> None:
        if len(self._conversation_history) <= COMPACTION_THRESHOLD:
            return

        workflow.logger.info(
            f"Compacting history for {chat_id}: "
            f"{len(self._conversation_history)} messages exceed threshold {COMPACTION_THRESHOLD}"
        )

        compact_output: CompactHistoryOutput = await workflow.execute_activity(
            "compact_history",
            arg=CompactHistoryInput(
                conversation_history=self._conversation_history,
                model=LLM_MODEL,
            ),
            result_type=CompactHistoryOutput,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        self._conversation_history = compact_output.compacted_history

        workflow.logger.info(
            f"Compacted {compact_output.original_message_count} → "
            f"{compact_output.compacted_message_count} messages for {chat_id}"
        )

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
            workflow.logger.warning(f"Failed to send status message: {exc}")

    async def _thinking_loop(self) -> None:
        for _ in range(MAX_TOOL_ITERATIONS):
            # temporal will not fail the workflow for non-determinism
            # if the workflow is replayed from a failure
            now = workflow.now().strftime("%Y-%m-%d %H:%M %Z")
            tool_docs = "\n\n".join(f"### {t.name}\n{t.body}" for t in self._tool_definitions)
            system_content = (
                f"Current time: {now}\n\n{SYSTEM_PROMPT}\n\n## Tool Documentation\n\n{tool_docs}"
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
                workflow.logger.info("No more tool calls. Exiting loop.")
                self._conversation_history.append(
                    {
                        "role": "assistant",
                        "content": llm_output.response_text,
                    }
                )
                # no more tools to call - exit function
                return

            tool_names = ", ".join(tc["function"]["name"] for tc in llm_output.tool_calls)
            await self._send_status(f"🔧 Using {tool_names}...")

            workflow.logger.info("Appending tool_call results to conversation history.")
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

            await self._send_status("🔍 Analyzing results...")

        # Hit max iterations
        workflow.logger.info(f"Maximum tool calls reached: {MAX_TOOL_ITERATIONS}")
        self._conversation_history.append(
            {
                "role": "assistant",
                "content": (
                    f"I've reached my thinking limit for this message "
                    f"({MAX_TOOL_ITERATIONS} iterations)."
                ),
            }
        )

    async def _dispatch(self, tool_call: dict) -> str:
        """Dispatch a single tool call to its handler via importlib convention.

        Tool name "bash" → openpaw.tool_handlers.bash → handle(args).
        """
        logger.info(f"Dispatching tool call for {tool_call}")
        func = tool_call["function"]
        name = func["name"]
        args = func["arguments"]

        try:
            with workflow.unsafe.imports_passed_through():
                mod = importlib.import_module(f"openpaw.tool_handlers.{name}")
        except ModuleNotFoundError:
            return f"Error: Unknown tool '{name}'"

        return await mod.handle(args, workflow_ref=self)
