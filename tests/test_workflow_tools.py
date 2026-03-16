from unittest.mock import patch

from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from opentlawpy.config import WHATSAPP_TASK_QUEUE
from opentlawpy.models.bash_command import BashCommandInput, BashCommandOutput
from opentlawpy.models.compaction import CompactHistoryInput, CompactHistoryOutput
from opentlawpy.models.file_operations import (
    ReadFileInput,
    ReadFileOutput,
    WriteFileInput,
    WriteFileOutput,
)
from opentlawpy.models.gather_tool_results import GatherToolResultsInput, GatherToolResultsOutput
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

TASK_QUEUE = "test-tool-tasks"

# Track activity calls for assertions
send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []
tool_command_calls: list[BashCommandInput] = []
read_file_calls: list[ReadFileInput] = []
write_file_calls: list[WriteFileInput] = []
gather_tool_results_calls: list[GatherToolResultsInput] = []


@activity.defn(name="send_whatsapp_message")
async def mock_send(input: SendMessageInput) -> SendMessageOutput:
    send_calls.append(input)
    return SendMessageOutput(text=input.text)


@activity.defn(name="execute_bash_command")
async def mock_execute_bash_command(input: BashCommandInput) -> BashCommandOutput:
    tool_command_calls.append(input)
    return BashCommandOutput(stdout="file1.txt\nfile2.txt", stderr="", exit_code=0, success=True)


@activity.defn(name="read_file_activity")
async def mock_read_file(input: ReadFileInput) -> ReadFileOutput:
    read_file_calls.append(input)
    return ReadFileOutput(content="file contents here", success=True)


@activity.defn(name="write_file_activity")
async def mock_write_file(input: WriteFileInput) -> WriteFileOutput:
    write_file_calls.append(input)
    return WriteFileOutput(success=True, bytes_written=len(input.content))


def _clear_all():
    send_calls.clear()
    llm_calls.clear()
    tool_command_calls.clear()
    read_file_calls.clear()
    write_file_calls.clear()
    gather_tool_results_calls.clear()


# Minimal tool definitions for testing (load_tools returns these)
MOCK_TOOLS = [
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
    ToolDefinition(
        name="read_file",
        description="Read a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        metadata={
            "type": "activity",
            "activity": "read_file_activity",
            "tier": "essential",
            "priority": 2,
        },
        body="Read file contents from the workspace.",
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


async def _run_workflow_with_mock_llm(mock_llm_fn):
    """Helper to run the workflow with a mocked call_llm and load_tools."""

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
                    mock_read_file,
                    mock_write_file,
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
                    chat_id="1234567890",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=True,
                ),
                id="test-wf-tools",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Hello"],
            )
            await handle.result()


async def test_workflow_no_tool_calls():
    """LLM returns text only — no tool loop, just sends the response."""
    _clear_all()

    def mock_llm(input: LLMCallInput) -> LLMCallOutput:
        return _make_text_response("Just a text reply")

    await _run_workflow_with_mock_llm(mock_llm)

    assert len(llm_calls) == 1
    assert len(tool_command_calls) == 0
    assert len(send_calls) == 1
    assert send_calls[0].text == "Just a text reply"


async def test_workflow_single_tool_call():
    """LLM requests one tool call, gets result, then responds with text."""
    _clear_all()
    call_count = 0

    def mock_llm(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": {"command": "ls"}},
                    }
                ],
                text="Let me check...",
            )
        return _make_text_response("Here are the files: file1.txt, file2.txt")

    await _run_workflow_with_mock_llm(mock_llm)

    assert len(llm_calls) == 2
    assert len(tool_command_calls) == 1
    assert tool_command_calls[0].command == "ls"
    assert len(send_calls) == 1
    assert send_calls[0].text == "Here are the files: file1.txt, file2.txt"

    # Second LLM call should include tool results in history
    second_call_messages = llm_calls[1].messages
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert "file1.txt" in tool_msgs[0]["content"]


async def test_workflow_tool_error_fed_back():
    """Tool fails — error message is returned to LLM, which adapts."""
    _clear_all()
    call_count = 0

    @activity.defn(name="execute_bash_command")
    async def mock_failing_command(input: BashCommandInput) -> BashCommandOutput:
        tool_command_calls.append(input)
        return BashCommandOutput(
            stdout="",
            stderr="No such file or directory",
            exit_code=1,
            success=False,
        )

    def mock_llm(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_err",
                        "type": "function",
                        "function": {"name": "bash", "arguments": {"command": "cat missing.txt"}},
                    }
                ],
            )
        return _make_text_response("Sorry, the file doesn't exist.")

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return mock_llm(input)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_failing_command,
                    mock_read_file,
                    mock_write_file,
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
                    chat_id="1234567890",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=True,
                ),
                id="test-wf-err",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Read missing.txt"],
            )
            try:
                await handle.result()
            except WorkflowFailureError as e:
                raise e.cause

    assert len(llm_calls) == 2
    # Error message should be in tool result
    second_call_messages = llm_calls[1].messages
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "Error" in tool_msgs[0]["content"]
    assert send_calls[0].text == "Sorry, the file doesn't exist."


async def test_workflow_max_iterations():
    """LLM always returns tool_calls — hits MAX_TOOL_ITERATIONS and sends limit message."""
    _clear_all()

    def mock_llm(input: LLMCallInput) -> LLMCallOutput:
        return _make_tool_response(
            tool_calls=[
                {
                    "id": f"call_{len(llm_calls)}",
                    "type": "function",
                    "function": {"name": "bash", "arguments": {"command": "echo loop"}},
                }
            ],
        )

    with patch("opentlawpy.workflows.agent_workflow.MAX_TOOL_ITERATIONS", 3):
        await _run_workflow_with_mock_llm(mock_llm)

    assert len(llm_calls) == 3
    assert len(send_calls) == 1
    assert "thinking limit" in send_calls[0].text


async def test_workflow_multiple_parallel_tools():
    """LLM returns 2 tool calls at once — both are executed."""
    _clear_all()
    call_count = 0

    def mock_llm(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "bash", "arguments": {"command": "ls"}},
                    },
                    {
                        "id": "call_b",
                        "type": "function",
                        "function": {"name": "bash", "arguments": {"command": "pwd"}},
                    },
                ],
                text="Let me check both...",
            )
        return _make_text_response("Done checking.")

    await _run_workflow_with_mock_llm(mock_llm)

    assert len(llm_calls) == 2
    assert len(tool_command_calls) == 2
    assert len(send_calls) == 1

    # Both tool results should be in the second LLM call
    second_call_messages = llm_calls[1].messages
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    tool_call_ids = {m["tool_call_id"] for m in tool_msgs}
    assert tool_call_ids == {"call_a", "call_b"}


async def test_workflow_llm_failure_sends_error_message():
    """LLM activity fails after retries — user gets an error message on WhatsApp."""
    _clear_all()

    @activity.defn(name="call_llm")
    async def mock_failing_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        raise RuntimeError("LLM provider is down")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_failing_llm,
                    mock_compact_history,
                    mock_execute_bash_command,
                    mock_read_file,
                    mock_write_file,
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
                    chat_id="1234567890",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=True,
                ),
                id="test-wf-llm-fail",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Hello"],
            )
            await handle.result()

    # User should still get a WhatsApp message
    assert len(send_calls) == 1
    assert "trouble processing" in send_calls[0].text


async def test_workflow_tool_activity_failure_fed_back_to_llm():
    """Tool activity crashes after retries — error fed back to LLM, LLM still responds."""
    _clear_all()
    call_count = 0

    def mock_llm(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_fail",
                        "type": "function",
                        "function": {"name": "bash", "arguments": {"command": "rm -rf /"}},
                    }
                ],
            )
        return _make_text_response("That command failed, sorry.")

    @activity.defn(name="execute_bash_command")
    async def mock_crashing_command(input: BashCommandInput) -> BashCommandOutput:
        return BashCommandOutput(
            stdout="",
            stderr=str("This is failed return."),
            exit_code=-1,
            success=False,
        )

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return mock_llm(input)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with (
            Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[AgentWorkflow, HeartbeatWorkflow, SubAgentWorkflow],
                activities=[
                    mock_call_llm,
                    mock_compact_history,
                    mock_crashing_command,
                    mock_read_file,
                    mock_write_file,
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
                    chat_id="1234567890",
                    output_activity="send_whatsapp_message",
                    output_task_queue=WHATSAPP_TASK_QUEUE,
                    enable_heartbeat=True,
                ),
                id="test-wf-tool-activity-fail",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Do something"],
            )
            try:
                await handle.result()
            except WorkflowFailureError as e:
                raise e.cause

    # LLM called twice: once to get tool call, once after error fed back
    assert len(llm_calls) == 2
    # Error was fed to LLM as a tool result
    second_call_messages = llm_calls[1].messages
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "Error" in tool_msgs[0]["content"]
    # LLM adapted and user got a response
    assert len(send_calls) == 1
    assert send_calls[0].text == "That command failed, sorry."
