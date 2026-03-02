from temporalio.client import Client

TASK_QUEUE = "agent-tasks"
NAMESPACE = "opentlawpy"


async def create_temporal_client(temporal_address: str) -> Client:
    """Create and return a Temporal client."""
    return await Client.connect(temporal_address, namespace=NAMESPACE)
