from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from opentlawpy.config import WHATSAPP_TASK_QUEUE
from opentlawpy.models.llm import LLMCallInput, LLMCallOutput
from opentlawpy.models.messages import SendMessageInput, SendMessageOutput
from opentlawpy.workflows.agent_workflow import AgentWorkflow

TASK_QUEUE = "test-agent-tasks"

# Track activity calls for assertions
send_calls: list[SendMessageInput] = []
llm_calls: list[LLMCallInput] = []


@activity.defn(name="send_whatsapp_message")
async def mock_send_whatsapp_message(input: SendMessageInput) -> SendMessageOutput:
    send_calls.append(input)
    return SendMessageOutput(success=True)


@activity.defn(name="call_llm")
async def mock_call_llm(input: LLMCallInput) -> LLMCallOutput:
    llm_calls.append(input)
    return LLMCallOutput(
        response_text=f"LLM response to: {input.messages[-1]['content']}",
        model_used=input.model,
        input_tokens=10,
        output_tokens=20,
    )


async def test_workflow_calls_llm_and_sends_response():
    """Start workflow with signal, verify it calls call_llm then send_whatsapp_message."""
    send_calls.clear()
    llm_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_call_llm],
        ), Worker(
            env.client,
            task_queue=WHATSAPP_TASK_QUEUE,
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

            await handle.result()

    assert len(llm_calls) == 1
    assert llm_calls[0].messages == [{"role": "user", "content": "Hi there"}]

    assert len(send_calls) == 1
    assert send_calls[0].phone_number == "1234567890"
    assert send_calls[0].text == "LLM response to: Hi there"


async def test_workflow_multiple_messages():
    """Workflow handles multiple messages, each getting an LLM response."""
    send_calls.clear()
    llm_calls.clear()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_call_llm],
        ), Worker(
            env.client,
            task_queue=WHATSAPP_TASK_QUEUE,
            activities=[mock_send_whatsapp_message],
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="5555555555",
                id="test-workflow-2",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["5555555555", "First message"],
            )

            await handle.signal(AgentWorkflow.new_message, args=["5555555555", "Second message"])

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
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AgentWorkflow],
            activities=[mock_call_llm],
        ), Worker(
            env.client,
            task_queue=WHATSAPP_TASK_QUEUE,
            activities=[mock_send_whatsapp_message],
        ):
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                arg="9999999999",
                id="test-workflow-3",
                task_queue=TASK_QUEUE,
                start_signal="new_message",
                start_signal_args=["9999999999", "Hello"],
            )

            await handle.signal(AgentWorkflow.new_message, args=["9999999999", "How are you?"])

            await handle.result()

    assert len(llm_calls) >= 2

    # First call: only the first user message
    assert llm_calls[0].messages == [{"role": "user", "content": "Hello"}]

    # Second call: full history (user + assistant + user)
    assert llm_calls[1].messages == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "LLM response to: Hello"},
        {"role": "user", "content": "How are you?"},
    ]
