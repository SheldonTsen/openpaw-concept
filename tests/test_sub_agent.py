from unittest.mock import patch

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from opentlawpy.config import WHATSAPP_TASK_QUEUE
from opentlawpy.models.bash_command import BashCommandInput, BashCommandOutput
from opentlawpy.models.compaction import CompactHistoryInput, CompactHistoryOutput
from opentlawpy.models.gather_tool_results import (
    GatherToolResultsInput,
    GatherToolResultsOutput,
)
from opentlawpy.models.heartbeat import PokeAgentInput, PokeAgentOutput
from opentlawpy.models.llm_call import LLMCallInput, LLMCallOutput
from opentlawpy.models.messages import AgentWorkflowInput, SendMessageInput, SendMessageOutput
from opentlawpy.models.state_io import (
    LoadStateInput,
    LoadStateOutput,
    SaveStateInput,
    SaveStateOutput,
)
from opentlawpy.models.sub_agent import SubAgentInput
from opentlawpy.models.tools import ToolDefinition
from opentlawpy.workflows.agent_workflow import AgentWorkflow
from opentlawpy.workflows.heartbeat_workflow import HeartbeatWorkflow
from opentlawpy.workflows.sub_agent_workflow import SubAgentWorkflow

TASK_QUEUE = "test-sub-agent-tasks"

# Track activity calls for assertions
send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []
gather_tool_results_calls: list[GatherToolResultsInput] = []


@activity.defn(name="send_whatsapp_message")
async def mock_send(input: SendMessageInput) -> SendMessageOutput:
    send_calls.append(input)
    return SendMessageOutput(text=input.text)


@activity.defn(name="execute_bash_command")
async def mock_execute_bash_command(input: BashCommandInput) -> BashCommandOutput:
    return BashCommandOutput(stdout="file1.txt\nfile2.txt", stderr="", exit_code=0, success=True)


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
        body="Execute shell commands.",
    ),
    ToolDefinition(
        name="delegate_task",
        description="Delegate a task to a sub-agent",
        parameters={
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
        metadata={"type": "workflow", "tier": "essential", "priority": 5},
        body="Delegate tasks to sub-agents.",
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


def _clear_all():
    send_calls.clear()
    llm_calls.clear()
    gather_tool_results_calls.clear()


ALL_ACTIVITIES = [
    mock_execute_bash_command,
    mock_compact_history,
    mock_load_tools,
    mock_gather_tool_results_activity,
    mock_save_state,
    mock_load_state,
    mock_poke_agent,
]


async def test_sub_agent_completes_task():
    """Sub-agent runs thinking loop and returns final text."""
    _clear_all()

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return _make_text_response("Task completed: found 2 files.")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[SubAgentWorkflow],
            activities=[mock_call_llm, *ALL_ACTIVITIES],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            result = await env.client.execute_workflow(
                SubAgentWorkflow.run,
                arg=SubAgentInput(task="List all files in the workspace"),
                id="test-sub-agent-1",
                task_queue=TASK_QUEUE,
            )

    assert result == "Task completed: found 2 files."
    assert len(llm_calls) == 1
    # Sub-agent should receive the task as a user message
    user_msgs = [m for m in llm_calls[0].messages if m["role"] == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "List all files in the workspace"


async def test_orchestrator_delegates_and_receives_result():
    """Full flow: orchestrator calls delegate_task, sub-agent runs, result fed back."""
    _clear_all()
    call_count = 0

    def mock_llm_fn(input: LLMCallInput) -> LLMCallOutput:
        nonlocal call_count
        call_count += 1

        # Check if this is a sub-agent call (no delegate_task in tools)
        tool_names = {t["function"]["name"] for t in input.tools} if input.tools else set()
        is_sub_agent = "delegate_task" not in tool_names

        if is_sub_agent:
            return _make_text_response("Sub-agent result: found 2 Python files.")

        # Orchestrator: first call delegates, second call uses result
        if call_count == 1:
            return _make_tool_response(
                tool_calls=[
                    {
                        "id": "call_delegate",
                        "type": "function",
                        "function": {
                            "name": "delegate_task",
                            "arguments": {"task": "Find all Python files"},
                        },
                    }
                ],
                text="Let me delegate this.",
            )
        return _make_text_response("Based on the sub-agent: there are 2 Python files.")

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
                activities=[mock_call_llm, *ALL_ACTIVITIES],
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
                ),
                id="test-orchestrator-delegate",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["Find all Python files in the project"],
            )
            await handle.result()

    # Orchestrator called LLM twice, sub-agent called once = 3 total
    assert len(llm_calls) == 3
    assert len(send_calls) == 1
    assert "2 Python files" in send_calls[0].text

    # The sub-agent's result should appear as a tool result in the orchestrator's second LLM call
    orchestrator_second_call = llm_calls[2]
    tool_msgs = [m for m in orchestrator_second_call.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "Sub-agent result" in tool_msgs[0]["content"]


async def test_sub_agent_excludes_delegate_task():
    """Sub-agent's tool list should not contain delegate_task."""
    _clear_all()

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return _make_text_response("Done.")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[SubAgentWorkflow],
            activities=[mock_call_llm, *ALL_ACTIVITIES],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            await env.client.execute_workflow(
                SubAgentWorkflow.run,
                arg=SubAgentInput(task="Do something"),
                id="test-sub-agent-no-delegate",
                task_queue=TASK_QUEUE,
            )

    assert len(llm_calls) == 1
    tool_names = {t["function"]["name"] for t in llm_calls[0].tools}
    assert "delegate_task" not in tool_names
    assert "bash" in tool_names


async def test_sub_agent_max_iterations():
    """Sub-agent hits iteration limit and returns partial result."""
    _clear_all()

    @activity.defn(name="call_llm")
    async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
        llm_calls.append(input)
        return _make_tool_response(
            tool_calls=[
                {
                    "id": f"call_{len(llm_calls)}",
                    "type": "function",
                    "function": {"name": "bash", "arguments": {"command": "echo loop"}},
                }
            ],
        )

    with patch("opentlawpy.workflows.sub_agent_workflow.SUB_AGENT_MAX_ITERATIONS", 3):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[SubAgentWorkflow],
                activities=[mock_call_llm, *ALL_ACTIVITIES],
                workflow_runner=UnsandboxedWorkflowRunner(),
            ):
                result = await env.client.execute_workflow(
                    SubAgentWorkflow.run,
                    arg=SubAgentInput(task="Keep looping"),
                    id="test-sub-agent-max-iter",
                    task_queue=TASK_QUEUE,
                )

    assert len(llm_calls) == 3
    assert "iteration limit" in result
