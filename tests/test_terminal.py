from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from opentlawpy.config import TERMINAL_TASK_QUEUE, WHATSAPP_TASK_QUEUE
from opentlawpy.models.compaction import CompactHistoryInput, CompactHistoryOutput
from opentlawpy.models.heartbeat import PokeAgentInput, PokeAgentOutput
from opentlawpy.models.llm_call import LLMCallInput, LLMCallOutput
from opentlawpy.models.messages import AgentWorkflowInput, SendMessageInput, SendMessageOutput
from opentlawpy.models.state_io import (
    LoadStateInput,
    LoadStateOutput,
    SaveStateInput,
    SaveStateOutput,
)
from opentlawpy.models.tools import ToolDefinition
from opentlawpy.workflows.agent_workflow import AgentWorkflow
from opentlawpy.workflows.heartbeat_workflow import HeartbeatWorkflow
from opentlawpy.workflows.sub_agent_workflow import SubAgentWorkflow

TASK_QUEUE = "test-terminal-tasks"

# Track activity calls
terminal_send_calls: list[SendMessageInput] = []
whatsapp_send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []


@activity.defn(name="send_terminal_message")
async def mock_send_terminal_message(input: SendMessageInput) -> SendMessageOutput:
    terminal_send_calls.append(input)
    return SendMessageOutput(text=input.text)


@activity.defn(name="send_whatsapp_message")
async def mock_send_whatsapp_message(input: SendMessageInput) -> SendMessageOutput:
    whatsapp_send_calls.append(input)
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
    mock_call_llm,
    mock_compact_history,
    mock_load_tools,
    mock_save_state,
    mock_load_state,
    mock_poke_agent,
]


async def test_terminal_workflow_routes_to_terminal_activity():
    """Workflow with terminal- prefix routes to send_terminal_message."""
    terminal_send_calls.clear()
    whatsapp_send_calls.clear()
    llm_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=DEFAULT_ACTIVITIES,
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=TERMINAL_TASK_QUEUE,
                activities=[mock_send_terminal_message],
            ),
            Worker(
                env.client,
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send_whatsapp_message],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=AgentWorkflowInput(
                    chat_id="session-abc",
                    output_activity="send_terminal_message",
                    output_task_queue=TERMINAL_TASK_QUEUE,
                ),
                id="terminal-session-abc",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Hello from terminal"],
            )

            await handle.result()

    # Should route to terminal, NOT whatsapp
    assert len(terminal_send_calls) == 1
    assert terminal_send_calls[0].phone_number == "session-abc"
    assert terminal_send_calls[0].text == "LLM response to: Hello from terminal"
    assert len(whatsapp_send_calls) == 0


async def test_non_terminal_workflow_routes_to_whatsapp():
    """Workflow without terminal- prefix routes to send_whatsapp_message."""
    terminal_send_calls.clear()
    whatsapp_send_calls.clear()
    llm_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=DEFAULT_ACTIVITIES,
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=TERMINAL_TASK_QUEUE,
                activities=[mock_send_terminal_message],
            ),
            Worker(
                env.client,
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send_whatsapp_message],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=AgentWorkflowInput(
                    chat_id="1234567890",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                ),
                id="whatsapp-1234567890",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Hello from WhatsApp"],
            )

            await handle.result()

    # Should route to whatsapp, NOT terminal
    assert len(whatsapp_send_calls) == 1
    assert whatsapp_send_calls[0].text == "LLM response to: Hello from WhatsApp"
    assert len(terminal_send_calls) == 0


async def test_send_terminal_message_activity_prints(capsys):
    """Unit test: send_terminal_message prints to stdout."""
    from opentlawpy.activities.terminal import send_terminal_message

    input_msg = SendMessageInput(phone_number="session-123", text="Hello world")
    result = await send_terminal_message(input_msg)

    assert result.text == "Hello world"
    assert "Hello world" in capsys.readouterr().out
