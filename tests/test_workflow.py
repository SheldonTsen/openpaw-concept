from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.models.messages import SendMessageInput, SendMessageOutput
from src.workflows.agent_workflow import AgentWorkflow

TASK_QUEUE = "test-agent-tasks"

# Track activity calls for assertions
activity_calls: list[SendMessageInput] = []


@activity.defn(name="send_whatsapp_message")
async def mock_send_whatsapp_message(input: SendMessageInput) -> SendMessageOutput:
    activity_calls.append(input)
    return SendMessageOutput(success=True)


async def test_workflow_echoes_message():
    """Workflow receives a signal and calls send_whatsapp_message with echo response."""
    activity_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_send_whatsapp_message],
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="1234567890",
                id="test-workflow-1",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["1234567890", "Hi there"],
            )

            # Time-skipping env auto-advances to the 60-min timeout
            await handle.result()

    assert len(activity_calls) == 1
    assert activity_calls[0].phone_number == "1234567890"
    assert activity_calls[0].text == "Hello! I received: Hi there"


async def test_workflow_start_signal_pattern():
    """Verify the atomic start-or-signal pattern works correctly."""
    activity_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_send_whatsapp_message],
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="9876543210",
                id="test-workflow-2",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["9876543210", "Hello world"],
            )

            await handle.result()

    assert len(activity_calls) >= 1
    assert activity_calls[0].phone_number == "9876543210"
    assert activity_calls[0].text == "Hello! I received: Hello world"


async def test_workflow_multiple_messages():
    """Workflow handles multiple messages in sequence."""
    activity_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_send_whatsapp_message],
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="5555555555",
                id="test-workflow-3",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["5555555555", "First message"],
            )

            # Send a second message
            await handle.signal(AgentWorkflow.new_message, args=["5555555555", "Second message"])

            await handle.result()

    assert len(activity_calls) >= 2
    assert activity_calls[0].text == "Hello! I received: First message"
    assert activity_calls[1].text == "Hello! I received: Second message"
