from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from opentlawpy.config import SYSTEM_PROMPT, WHATSAPP_TASK_QUEUE
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


def _is_system_message(msg: dict) -> bool:
    """Check that a message is the dynamic system prompt (with current-time prefix)."""
    return (
        msg["role"] == "system"
        and SYSTEM_PROMPT in msg["content"]
        and msg["content"].startswith("Current time:")
    )


TASK_QUEUE = "test-agent-tasks"

# Track activity calls for assertions
send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []
save_state_calls: list[SaveStateInput] = []


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


async def test_workflow_calls_llm_and_sends_response():
    """Start workflow with signal, verify it calls call_llm then send_whatsapp_message."""
    send_calls.clear()
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
                id="test-workflow-1",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Hi there"],
            )

            await handle.result()

    assert len(llm_calls) == 1
    assert _is_system_message(llm_calls[0].messages[0])
    assert llm_calls[0].messages[1:] == [
        {"role": "user", "content": "Hi there"},
    ]

    assert len(send_calls) == 1
    assert send_calls[0].phone_number == "1234567890"
    assert send_calls[0].text == "LLM response to: Hi there"


async def test_workflow_multiple_messages():
    """Workflow handles multiple messages, each getting an LLM response."""
    send_calls.clear()
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
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send_whatsapp_message],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=AgentWorkflowInput(
                    chat_id="5555555555",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                ),
                id="test-workflow-2",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["First message"],
            )

            await handle.signal(AgentWorkflow.new_message, args=["Second message"])

            await handle.result()

    assert len(llm_calls) >= 2
    assert len(send_calls) >= 2
    assert send_calls[0].text == "LLM response to: First message"
    assert send_calls[1].text == "LLM response to: Second message"


async def test_workflow_sends_conversation_history():
    """Second LLM call receives full conversation history (user1 + assistant1 + user2)."""
    send_calls.clear()
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
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send_whatsapp_message],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=AgentWorkflowInput(
                    chat_id="9999999999",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                ),
                id="test-workflow-3",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Hello"],
            )

            await handle.signal(AgentWorkflow.new_message, args=["How are you?"])

            await handle.result()

    assert len(llm_calls) >= 2

    # First call: system prompt + first user message
    assert _is_system_message(llm_calls[0].messages[0])
    assert llm_calls[0].messages[1:] == [
        {"role": "user", "content": "Hello"},
    ]

    # Second call: system prompt + full history (user + assistant + user)
    assert _is_system_message(llm_calls[1].messages[0])
    assert llm_calls[1].messages[1:] == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "LLM response to: Hello"},
        {"role": "user", "content": "How are you?"},
    ]


async def test_system_prompt_prepended_to_every_llm_call():
    """System prompt is the first message in every LLM call, not stored in history."""
    send_calls.clear()
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
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send_whatsapp_message],
            ),
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=AgentWorkflowInput(
                    chat_id="7777777777",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                ),
                id="test-workflow-4",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Msg1"],
            )

            await handle.signal(AgentWorkflow.new_message, args=["Msg2"])

            await handle.result()

    assert len(llm_calls) >= 2

    for call in llm_calls:
        assert _is_system_message(call.messages[0])

    for call in llm_calls:
        system_messages = [m for m in call.messages if m["role"] == "system"]
        assert len(system_messages) == 1


async def test_workflow_loads_persisted_state():
    """Workflow loads pre-existing conversation history on startup."""
    send_calls.clear()
    llm_calls.clear()
    save_state_calls.clear()

    persisted = LoadStateOutput(
        conversation_history=[
            {"role": "user", "content": "Previous message"},
            {"role": "assistant", "content": "Previous response"},
        ],
        found=True,
    )

    @activity.defn(name="load_state_activity")
    async def load_state_with_history(input: LoadStateInput) -> LoadStateOutput:
        return persisted

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_load_tools,
                    mock_save_state,
                    load_state_with_history,
                    mock_poke_agent,
                ],
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
                arg=AgentWorkflowInput(
                    chat_id="8888888888",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                ),
                id="test-workflow-persist",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["New message"],
            )

            await handle.result()

    assert len(llm_calls) == 1

    messages = llm_calls[0].messages
    assert _is_system_message(messages[0])
    assert messages[1] == {"role": "user", "content": "Previous message"}
    assert messages[2] == {"role": "assistant", "content": "Previous response"}
    assert messages[3] == {"role": "user", "content": "New message"}

    assert len(save_state_calls) >= 1
    saved_history = save_state_calls[-1].conversation_history
    assert len(saved_history) == 4


async def test_workflow_triggers_compaction():
    """Compaction is triggered when history exceeds COMPACTION_THRESHOLD."""
    send_calls.clear()
    llm_calls.clear()
    save_state_calls.clear()

    preloaded_history = []
    for i in range(50):
        role = "user" if i % 2 == 0 else "assistant"
        preloaded_history.append({"role": role, "content": f"Old message {i}"})

    persisted = LoadStateOutput(
        conversation_history=preloaded_history,
        found=True,
    )

    @activity.defn(name="load_state_activity")
    async def load_state_with_history(input: LoadStateInput) -> LoadStateOutput:
        return persisted

    compact_calls: list[CompactHistoryInput] = []

    @activity.defn(name="compact_history")
    async def tracking_compact_history(input: CompactHistoryInput) -> CompactHistoryOutput:
        compact_calls.append(input)
        summary = {
            "role": "system",
            "content": "[CONVERSATION SUMMARY]\nSummary of old messages.",
        }
        return CompactHistoryOutput(
            compacted_history=[summary] + input.conversation_history[-2:],
            original_message_count=len(input.conversation_history),
            compacted_message_count=3,
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    tracking_compact_history,
                    mock_load_tools,
                    mock_save_state,
                    load_state_with_history,
                    mock_poke_agent,
                ],
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
                arg=AgentWorkflowInput(
                    chat_id="compact-test-2",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                ),
                id="test-workflow-compact-2",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Trigger compaction"],
            )

            await handle.result()

    assert len(compact_calls) == 1
    assert compact_calls[0].conversation_history[-1]["role"] == "assistant"

    last_save = save_state_calls[-1]
    assert len(last_save.conversation_history) == 3


async def test_workflow_restart_preserves_state():
    """Workflow 2 loads state saved by workflow 1, proving cross-restart persistence."""
    send_calls.clear()
    llm_calls.clear()
    save_state_calls.clear()

    saved_history: list[dict] = []

    @activity.defn(name="save_state_activity")
    async def bridging_save_state(input: SaveStateInput) -> SaveStateOutput:
        save_state_calls.append(input)
        saved_history.clear()
        saved_history.extend(input.conversation_history)
        return SaveStateOutput(success=True)

    @activity.defn(name="load_state_activity")
    async def bridging_load_state(input: LoadStateInput) -> LoadStateOutput:
        if saved_history:
            return LoadStateOutput(conversation_history=list(saved_history), found=True)
        return LoadStateOutput(conversation_history=[], found=False)

    activities = [
        mock_call_llm,
        mock_compact_history,
        mock_load_tools,
        bridging_save_state,
        bridging_load_state,
        mock_poke_agent,
    ]

    chat_id = "restart-test-phone"
    wf_input = AgentWorkflowInput(
        chat_id=chat_id,
        output_activity="send_whatsapp_message",
        output_task_queue=WHATSAPP_TASK_QUEUE,
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=activities,
                workflow_runner=UnsandboxedWorkflowRunner(),
            ),
            Worker(
                env.client,
                task_queue=WHATSAPP_TASK_QUEUE,
                activities=[mock_send_whatsapp_message],
            ),
        ):
            handle1 = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=wf_input,
                id="test-restart-wf-1",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["First message"],
            )
            await handle1.result()

            assert len(save_state_calls) == 1
            assert saved_history == [
                {"role": "user", "content": "First message"},
                {"role": "assistant", "content": "LLM response to: First message"},
            ]

            handle2 = await env.client.start_workflow(
                AgentWorkflow.run,
                arg=wf_input,
                id="test-restart-wf-2",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Second message"],
            )
            await handle2.result()

    assert len(llm_calls) == 2

    wf2_messages = llm_calls[1].messages
    assert _is_system_message(wf2_messages[0])
    assert wf2_messages[1:] == [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "LLM response to: First message"},
        {"role": "user", "content": "Second message"},
    ]

    assert len(save_state_calls) == 2
