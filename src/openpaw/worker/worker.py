from temporalio.client import Client

from openpaw.config import NAMESPACE


async def create_temporal_client(temporal_address: str) -> Client:
    """Create and return a Temporal client."""
    return await Client.connect(temporal_address, namespace=NAMESPACE)
