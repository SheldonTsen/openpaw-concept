import asyncio

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from openpaw.config import WHATSAPP_TASK_QUEUE
from openpaw.models.bash_command import BashCommandInput, BashCommandOutput
from openpaw.models.compaction import CompactHistoryInput, CompactHistoryOutput
from openpaw.models.gather_tool_results import GatherToolResultsInput, GatherToolResultsOutput
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

TASK_QUEUE = "test-approval-tasks"

# Track activity calls for assertions
send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []
tool_command_calls: list[BashCommandInput] = []
gather_tool_results_calls: list[GatherToolResultsInput] = []


@activity.defn(name="send_whatsapp_message")
async def mock_send(input: SendMessageInput) -> SendMessageOutput:
    send_calls.append(input)
    return SendMessageOutput(text=input.text)


@activity.defn(name="execute_bash_command")
async def mock_execute_bash_command(input: BashCommandInput) -> BashCommandOutput:
    tool_command_calls.append(input)
    return BashCommandOutput(stdout="command output", stderr="", exit_code=0, success=True)


MOCK_TOOLS = [
    ToolDefinition(
        name="bash_with_approval",
        description="Run bash with approval",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        metadata={"type": "cli", "tier": "essential", "priority": 2},
        body="Execute bash commands with human approval.",
    ),
    ToolDefinition(
        name="bash",
        description="Run bash",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        metadata={"type": "cli", "tier": "essential", "priority": 1},
        body="Execute shell commands in a sandboxed container.",
    ),
]


@activity.defn(name="load_tools_activity")
async def mock_load_tools() -> list[ToolDefinition]:
    return MOCK_TOOLS


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


@activity.defn(name="gather_tool_results_activity")
async def mock_gather_tool_results_activity(
    input: GatherToolResultsInput,
) -> GatherToolResultsOutput:
    gather_tool_results_calls.append(input)

    num_res = []
    for tc, result in zip(input.tool_calls, input.tool_results):
        if isinstance(result, Exception):
            content = f"Error: {result}"
        else:
            content = result
        num_res.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": content,
            }
        )

    return GatherToolResultsOutput(tool_results_as_messages=num_res)


def _clear_all():
    send_calls.clear()
    llm_calls.clear()
    tool_command_calls.clear()
    gather_tool_results_calls.clear()


def _make_text_response(text: str) -> LLMCallOutput:
    return LLMCallOutput(
        response_text=text,
        model_used="test-model",
        input_tokens=10,
        output_tokens=20,
        tool_calls=[],
        stop_reason="stop",
    )


def _make_tool_response(tool_calls: list[dict], text: str = "") -> LLMCallOutput:
    return LLMCallOutput(
        response_text=text,
        model_used="test-model",
        input_tokens=10,
        output_tokens=20,
        tool_calls=tool_calls,
        stop_reason="tool_calls",
    )


async def test_approval_granted():
    """Signal YES → command runs, result returned to LLM."""
    _clear_all()
    call_count = 0

    def mock_llm_fn(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_approve",
                        "type": "function",
                        "function": {
                            "name": "bash_with_approval",
                            "arguments": {"command": "echo hello"},
                        },
                    }
                ],
            )
        return _make_text_response("Command ran successfully.")

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return mock_llm_fn(input)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_execute_bash_command,
                    mock_load_tools,
                    mock_gather_tool_results_activity,
                    mock_save_state,
                    mock_load_state,
                    mock_poke_agent,
                ],
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
                arg=AgentWorkflowInput(
                    chat_id="approval-test-1",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=False,
                ),
                id="test-approval-granted",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Delete temp files"],
            )

            # Wait a moment for the approval request to be sent
            await asyncio.sleep(0.5)

            # Signal YES
            await handle.signal(AgentWorkflow.new_message, args=["YES"])

            await handle.result()

    # Bash command should have been executed
    assert len(tool_command_calls) == 1
    assert tool_command_calls[0].command == "echo hello"

    # LLM called twice: once to get tool call, once after tool result
    assert len(llm_calls) == 2

    # Final response to user
    assert send_calls[-1].text == "Command ran successfully."

    # Approval request message should be in send_calls
    approval_msgs = [s for s in send_calls if "Approval needed" in s.text]
    assert len(approval_msgs) == 1


async def test_approval_denied():
    """Signal NO → command not run, error string returned to LLM."""
    _clear_all()
    call_count = 0

    def mock_llm_fn(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_deny",
                        "type": "function",
                        "function": {
                            "name": "bash_with_approval",
                            "arguments": {"command": "rm -rf /"},
                        },
                    }
                ],
            )
        return _make_text_response("OK, I won't run that command.")

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return mock_llm_fn(input)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_execute_bash_command,
                    mock_load_tools,
                    mock_gather_tool_results_activity,
                    mock_save_state,
                    mock_load_state,
                    mock_poke_agent,
                ],
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
                arg=AgentWorkflowInput(
                    chat_id="approval-test-2",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=False,
                ),
                id="test-approval-denied",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Delete everything"],
            )

            await asyncio.sleep(0.5)

            # Signal NO
            await handle.signal(AgentWorkflow.new_message, args=["NO"])

            await handle.result()

    # Bash command should NOT have been executed
    assert len(tool_command_calls) == 0

    # LLM called twice: once to get tool call, once after denial error
    assert len(llm_calls) == 2

    # Second LLM call should have the denial error in tool results
    second_call_messages = llm_calls[1].messages
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "denied" in tool_msgs[0]["content"].lower()


async def test_approval_timeout():
    """No signal → approval times out, error string returned to LLM."""
    _clear_all()
    call_count = 0

    def mock_llm_fn(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_timeout",
                        "type": "function",
                        "function": {
                            "name": "bash_with_approval",
                            "arguments": {"command": "echo timeout"},
                        },
                    }
                ],
            )
        return _make_text_response("The command timed out waiting for approval.")

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return mock_llm_fn(input)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_execute_bash_command,
                    mock_load_tools,
                    mock_gather_tool_results_activity,
                    mock_save_state,
                    mock_load_state,
                    mock_poke_agent,
                ],
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
                arg=AgentWorkflowInput(
                    chat_id="approval-test-3",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=False,
                ),
                id="test-approval-timeout",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Run something"],
            )

            # Don't signal anything — let approval timeout
            # Time-skipping env will auto-advance the 5 min timeout
            await handle.result()

    # Bash command should NOT have been executed
    assert len(tool_command_calls) == 0

    # LLM called twice: once to get tool call, once after timeout error
    assert len(llm_calls) == 2

    # Second LLM call should have the timeout error in tool results
    second_call_messages = llm_calls[1].messages
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "timed out" in tool_msgs[0]["content"].lower()


async def test_regular_bash_unchanged():
    """Regular bash tool still works without approval gate."""
    _clear_all()
    call_count = 0

    def mock_llm_fn(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_bash",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": {"command": "ls"},
                        },
                    }
                ],
            )
        return _make_text_response("Here are the files.")

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return mock_llm_fn(input)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_execute_bash_command,
                    mock_load_tools,
                    mock_gather_tool_results_activity,
                    mock_save_state,
                    mock_load_state,
                    mock_poke_agent,
                ],
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
                arg=AgentWorkflowInput(
                    chat_id="approval-test-4",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=False,
                ),
                id="test-bash-no-approval",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["List files"],
            )

            # No need to signal YES — regular bash runs immediately
            await handle.result()

    # Bash command should have been executed immediately (no approval needed)
    assert len(tool_command_calls) == 1
    assert tool_command_calls[0].command == "ls"

    # LLM called twice: once to get tool call, once after result
    assert len(llm_calls) == 2
    assert send_calls[-1].text == "Here are the files."


async def test_sub_agent_approval_forwarded():
    """Parent forwards YES signal to sub-agent child workflow for approval."""
    _clear_all()

    # Orchestrator LLM: delegates to sub-agent on first call
    orchestrator_call_count = 0

    def orchestrator_llm_fn(input: LLMCallInput) -> LLMCallOutput:
        nonlocal orchestrator_call_count
        orchestrator_call_count += 1
        if orchestrator_call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_delegate",
                        "type": "function",
                        "function": {
                            "name": "delegate_task",
                            "arguments": {"task": "Run echo hello with approval"},
                        },
                    }
                ],
            )
        return _make_text_response("Sub-agent completed the task.")

    # Sub-agent LLM: calls bash_with_approval on first call
    sub_agent_call_count = 0

    def sub_agent_llm_fn(input: LLMCallInput) -> LLMCallOutput:
        nonlocal sub_agent_call_count
        sub_agent_call_count += 1
        if sub_agent_call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_sub_approve",
                        "type": "function",
                        "function": {
                            "name": "bash_with_approval",
                            "arguments": {"command": "echo hello"},
                        },
                    }
                ],
            )
        return _make_text_response("Done running the command.")

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        # Route based on whether this is a sub-agent or orchestrator call
        # Sub-agent calls have a task-seeded user message
        first_user = next((m for m in input.messages if m["role"] == "user"), None)
        if first_user and "Run echo hello with approval" in first_user.get("content", ""):
            return sub_agent_llm_fn(input)
        return orchestrator_llm_fn(input)

    # Include delegate_task in mock tools so orchestrator can use it
    mock_tools_with_delegate = MOCK_TOOLS + [
        ToolDefinition(
            name="delegate_task",
            description="Delegate task to sub-agent",
            parameters={
                "type": "object",
                "properties": {"task": {"type": "string"}},
                "required": ["task"],
            },
            metadata={"type": "workflow", "tier": "essential", "priority": 3},
            body="Delegate a task to a sub-agent.",
        ),
    ]

    @activity.defn(name="load_tools_activity")
    async def mock_load_tools_with_delegate() -> list[ToolDefinition]:
        return mock_tools_with_delegate

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_execute_bash_command,
                    mock_load_tools_with_delegate,
                    mock_gather_tool_results_activity,
                    mock_save_state,
                    mock_load_state,
                    mock_poke_agent,
                ],
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
                arg=AgentWorkflowInput(
                    chat_id="approval-sub-test",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=False,
                ),
                id="test-sub-agent-approval",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Please delegate this"],
            )

            # Wait for the sub-agent to send the approval request
            await asyncio.sleep(0.5)

            # Signal YES to the PARENT — it should forward to the child
            await handle.signal(AgentWorkflow.new_message, args=["YES"])

            await handle.result()

    # Bash command should have been executed via the sub-agent
    assert len(tool_command_calls) == 1
    assert tool_command_calls[0].command == "echo hello"

    # Approval request should have been sent to user
    approval_msgs = [s for s in send_calls if "Approval needed" in s.text]
    assert len(approval_msgs) == 1
