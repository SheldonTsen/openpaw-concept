from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from openpaw.config import WHATSAPP_TASK_QUEUE
from openpaw.models.compaction import CompactHistoryInput, CompactHistoryOutput
from openpaw.models.heartbeat import PokeAgentInput, PokeAgentOutput
from openpaw.models.llm_call import LLMCallInput, LLMCallOutput
from openpaw.models.messages import AgentWorkflowInput, SendMessageInput, SendMessageOutput
from openpaw.models.state_io import (
    LoadStateInput,
    LoadStateOutput,
    SaveStateInput,
    SaveStateOutput,
)
from openpaw.models.tools import ToolDefinition
from openpaw.workflows.agent_workflow import AgentWorkflow
from openpaw.workflows.heartbeat_workflow import HeartbeatWorkflow
from openpaw.workflows.sub_agent_workflow import SubAgentWorkflow

TASK_QUEUE = "test-btw-tasks"

send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []


@activity.defn(name="send_whatsapp_message")
async def mock_send(input: SendMessageInput) -> SendMessageOutput:
    send_calls.append(input)
    return SendMessageOutput(text=input.text)


@activity.defn(name="load_tools_activity")
async def mock_load_tools() -> list[ToolDefinition]:
    return []


@activity.defn(name="save_state_activity")
async def mock_save_state(input: SaveStateInput) -> SaveStateOutput:
    return SaveStateOutput(success=True)


@activity.defn(name="compact_history")
async def mock_compact_history(input: CompactHistoryInput) -> CompactHistoryOutput:
    return CompactHistoryOutput(
        compacted_history=input.conversation_history,
        original_message_count=len(input.conversation_history),
        compacted_message_count=len(input.conversation_history),
    )


@activity.defn(name="load_state_activity")
async def mock_load_state(input: LoadStateInput) -> LoadStateOutput:
    return LoadStateOutput(conversation_history=[], found=False)


@activity.defn(name="poke_agent")
async def mock_poke_agent(input: PokeAgentInput) -> PokeAgentOutput:
    return PokeAgentOutput(success=True)


DEFAULT_ACTIVITIES = [
    mock_compact_history,
    mock_load_tools,
    mock_save_state,
    mock_load_state,
    mock_poke_agent,
]

_AGENT_INPUT = AgentWorkflowInput(
    chat_id="1234567890",
    output_activity="send_whatsapp_message",
    output_task_queue=WHATSAPP_TASK_QUEUE,
    enable_heartbeat=False,
)


async def test_btw_spawns_child_and_sends_response():
    """Sending /btw fires a child SubAgent that sends its answer directly to the user.

    The main workflow is never unblocked (no regular message), so it times out.
    The btw child completes independently and sends a response.
    """
    send_calls.clear()
    llm_calls.clear()

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return LLMCallOutput(
            response_text="The answer is 42.",
            model_used="test-model",
            input_tokens=10,
            output_tokens=5,
            tool_calls=[],
            stop_reason="stop",
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[mock_call_llm, *DEFAULT_ACTIVITIES],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=_AGENT_INPUT,
                id="test-btw-basic",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["/btw What is the meaning of life?"],
            )
            # Parent workflow times out (no regular message sent). Time-skipping advances automatically.
            await handle.result()

    # The child SubAgent should have sent its answer
    assert len(send_calls) == 1
    assert send_calls[0].text == "The answer is 42."
    assert send_calls[0].phone_number == "1234567890"

    # The LLM call was for the child — the question should NOT include the /btw prefix
    assert len(llm_calls) == 1
    user_msgs = [m for m in llm_calls[0].messages if m["role"] == "user"]
    assert user_msgs[-1]["content"] == "What is the meaning of life?"


async def test_btw_does_not_add_to_pending_messages():
    """/btw messages must not be queued as regular messages — main workflow stays idle."""
    send_calls.clear()
    llm_calls.clear()

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return LLMCallOutput(
            response_text="btw response",
            model_used="test-model",
            input_tokens=10,
            output_tokens=5,
            tool_calls=[],
            stop_reason="stop",
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[mock_call_llm, *DEFAULT_ACTIVITIES],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=_AGENT_INPUT,
                id="test-btw-no-pending",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["/btw side question"],
            )
            await handle.result()

    # Only 1 LLM call: the child. The parent never called the LLM.
    # If /btw had been treated as a regular message the parent would also call LLM,
    # and the child would make it 2 total. Only 1 means only the child ran.
    assert len(llm_calls) == 1

    # The parent never sent a response (only the child did)
    assert len(send_calls) == 1


async def test_btw_passes_conversation_history_as_context():
    """/btw child receives a snapshot of the current conversation history."""
    send_calls.clear()
    llm_calls.clear()

    existing_history = [
        {"role": "user", "content": "What files are in the workspace?"},
        {"role": "assistant", "content": "I found main.py and utils.py."},
    ]

    @activity.defn(name="load_state_activity")
    async def mock_load_state_with_history(input: LoadStateInput) -> LoadStateOutput:
        return LoadStateOutput(conversation_history=existing_history, found=True)

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return LLMCallOutput(
            response_text="Context-aware answer.",
            model_used="test-model",
            input_tokens=10,
            output_tokens=5,
            tool_calls=[],
            stop_reason="stop",
        )

    activities_with_history = [
        mock_call_llm,
        mock_compact_history,
        mock_load_tools,
        mock_save_state,
        mock_load_state_with_history,
        mock_poke_agent,
    ]

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=activities_with_history,
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=_AGENT_INPUT,
                id="test-btw-history",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["/btw Which file has the main function?"],
            )
            await handle.result()

    # The child's LLM call should include the prior conversation as context
    assert len(llm_calls) == 1
    history_in_call = [m for m in llm_calls[0].messages if m["role"] != "system"]
    # existing history (2 msgs) + the btw question (1 msg) = 3
    assert len(history_in_call) == 3
    assert history_in_call[0] == existing_history[0]
    assert history_in_call[1] == existing_history[1]
    assert history_in_call[2]["role"] == "user"
    assert history_in_call[2]["content"] == "Which file has the main function?"
