from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from opentlawpy.config import HEARTBEAT_MESSAGE, WHATSAPP_TASK_QUEUE
from opentlawpy.models.compaction import CompactHistoryInput, CompactHistoryOutput
from opentlawpy.models.heartbeat import PokeAgentInput, PokeAgentOutput
from opentlawpy.models.llm_call import LLMCallInput, LLMCallOutput
from opentlawpy.models.messages import SendMessageInput, SendMessageOutput
from opentlawpy.models.state_io import (
    LoadStateInput,
    LoadStateOutput,
    SaveStateInput,
    SaveStateOutput,
)
from opentlawpy.models.tools import ToolDefinition
from opentlawpy.workflows.agent_workflow import AgentWorkflow
from opentlawpy.workflows.heartbeat_workflow import HeartbeatWorkflow

TASK_QUEUE = "test-heartbeat-tasks"

# Track activity calls
poke_calls: list[PokeAgentInput] = []
send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []
save_state_calls: list[SaveStateInput] = []


@activity.defn(name="poke_agent")
async def mock_poke_agent(input: PokeAgentInput) -> PokeAgentOutput:
    poke_calls.append(input)
    return PokeAgentOutput(success=True)


@activity.defn(name="send_whatsapp_message")
async def mock_send_whatsapp_message(input: SendMessageInput) -> SendMessageOutput:
    send_calls.append(input)
    return SendMessageOutput(text=input.text)


@activity.defn(name="call_llm")
async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
    llm_calls.append(input)
    return LLMCallOutput(
        response_text=f"LLM response to: {input.messages[-1]['content']}",
        model_used=input.model,
        input_tokens=10,
        output_tokens=20,
    )


@activity.defn(name="load_tools_activity")
async def mock_load_tools() -> list[ToolDefinition]:
    return []


@activity.defn(name="save_state_activity")
async def mock_save_state(input: SaveStateInput) -> SaveStateOutput:
    save_state_calls.append(input)
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


HEARTBEAT_ACTIVITIES = [mock_poke_agent]

AGENT_ACTIVITIES = [
    mock_call_llm,
    mock_compact_history,
    mock_load_tools,
    mock_save_state,
    mock_load_state,
]


async def test_heartbeat_pokes_agent_after_interval():
    """HeartbeatWorkflow calls poke_agent after the sleep interval."""
    poke_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[HeartbeatWorkflow],
            activities=HEARTBEAT_ACTIVITIES,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                HeartbeatWorkflow.run,
                arg="test-chat-1",
                id="test-heartbeat-1",
                task_queue=TASK_QUEUE,
            )

            # Advance time past the heartbeat interval to trigger a poke
            await env.sleep(31 * 60)

            # Stop the heartbeat
            await handle.signal(HeartbeatWorkflow.stop)
            await handle.result()

    assert len(poke_calls) >= 1
    assert poke_calls[0].chat_id == "test-chat-1"
    assert poke_calls[0].message == HEARTBEAT_MESSAGE


async def test_heartbeat_stop_signal():
    """HeartbeatWorkflow exits cleanly on stop signal."""
    poke_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[HeartbeatWorkflow],
            activities=HEARTBEAT_ACTIVITIES,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                HeartbeatWorkflow.run,
                arg="test-chat-2",
                id="test-heartbeat-2",
                task_queue=TASK_QUEUE,
            )

            # Send stop immediately
            await handle.signal(HeartbeatWorkflow.stop)
            await handle.result()

    # Should exit without poking (stop signal arrived before first timeout)
    assert len(poke_calls) == 0


async def test_heartbeat_stop_during_sleep():
    """Stop signal wakes the heartbeat from sleep and exits immediately."""
    poke_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[HeartbeatWorkflow],
            activities=HEARTBEAT_ACTIVITIES,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await env.client.start_workflow(
                HeartbeatWorkflow.run,
                arg="test-chat-3",
                id="test-heartbeat-3",
                task_queue=TASK_QUEUE,
            )

            # Advance time past one interval so a poke fires
            await env.sleep(31 * 60)

            # Now stop during next sleep cycle
            await handle.signal(HeartbeatWorkflow.stop)
            await handle.result()

    # At least one poke happened, then clean exit
    assert len(poke_calls) >= 1


async def test_agent_starts_heartbeat():
    """AgentWorkflow starts HeartbeatWorkflow as a child workflow."""
    poke_calls.clear()
    send_calls.clear()
    llm_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow],
                activities=AGENT_ACTIVITIES + HEARTBEAT_ACTIVITIES,
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send_whatsapp_message],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="test-chat-4",
                id="whatsapp-test-chat-4",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Hello"],
            )

            # Agent should process the message and time out
            await handle.result()

    # Agent processed the message
    assert len(llm_calls) >= 1
    assert len(send_calls) >= 1

    # Heartbeat was started (at least one poke happened during agent's idle timeout)
    assert len(poke_calls) >= 1
