# WhatsApp Integration Plan: Green API (Polling - No Public URL)

See also: https://green-api.com/en/docs/before-start/#cabinet

## Executive Summary

This document provides a complete implementation plan for integrating WhatsApp into the Temporal-based agent system using **Green API**. Green API is a third-party WhatsApp Business API service that supports **HTTP polling**, eliminating the need for a public-facing URL.

**Key Benefits:**
- ✅ No public URL required (polling-based)
- ✅ Official Python library
- ✅ Production-ready and stable
- ✅ 24-hour message queue (resilient to downtime)
- ✅ Free developer tier for testing
- ✅ Simple integration with Temporal workflows

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Green API Setup](#green-api-setup)
3. [Implementation](#implementation)
4. [Temporal Integration](#temporal-integration)
5. [Deployment](#deployment)
6. [Testing Strategy](#testing-strategy)
7. [Monitoring & Operations](#monitoring--operations)
8. [Cost Analysis](#cost-analysis)
9. [Pros & Cons](#pros--cons)
10. [Migration Path](#migration-path)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   WhatsApp User                          │
│                  (Mobile App)                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Green API Service (Cloud)                   │
│  - Manages WhatsApp Business API connection             │
│  - Stores messages in queue (24h retention)             │
│  - Provides HTTP API for send/receive                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ HTTP Polling (every 5s)
                     ▼
┌─────────────────────────────────────────────────────────┐
│          WhatsApp Poller Service (Python)                │
│  - Polls Green API for new messages                     │
│  - Routes to Temporal workflows via signals             │
│  - Runs as background service                           │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Temporal Signals
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Temporal Workflows                          │
│  - Agent workflows process messages                     │
│  - Execute LLM calls and tools                          │
│  - Trigger send activity for responses                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Activity Call
                     ▼
┌─────────────────────────────────────────────────────────┐
│         WhatsApp Send Activity (Python)                  │
│  - Calls Green API HTTP endpoint                        │
│  - Sends response messages                              │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

**Incoming Message:**
```
WhatsApp User → Green API → Message Queue → Poller Service →
Temporal Signal → Agent Workflow → LLM Processing →
Send Activity → Green API → WhatsApp User
```

**Key Points:**
- **No webhooks:** Poller initiates all connections (outbound)
- **No public URL:** Everything runs on private network
- **Queue-based:** Messages stored up to 24 hours
- **Polling interval:** Configurable (recommended: 5 seconds)

---

## Green API Setup

### Step 1: Account Registration

1. **Sign up** at [green-api.com](https://green-api.com/en)
2. **Verify email** and create instance
3. **Choose plan:**
   - Developer (Free): Limited messages for testing
   - Business: Starting at ~$20/month

### Step 2: Get Credentials

1. Go to [Green API Console](https://console.green-api.com/)
2. Click your instance
3. Copy:
   - **Instance ID** (e.g., `1101000001`)
   - **API Token** (e.g., `d75b3a66374942c5b3c019c698abc2067e151558acbd412345`)

### Step 3: Link WhatsApp Account

1. In console, click "Scan QR Code"
2. Open WhatsApp on your phone
3. Go to Settings → Linked Devices
4. Scan the QR code from Green API console
5. Wait for "Connected" status

**Note:** You can link a phone number you already use - it won't disconnect your phone app.

### Step 4: Configure Instance (Optional)

In Green API console, configure:
- **Webhook settings:** Leave empty (we're using polling)
- **Incoming webhooks:** Enable "incomingMessageReceived"
- **Outgoing webhooks:** Enable if you want to track sent messages
- **State webhooks:** Optional (for connection status)

---

## Implementation

### File Structure

```
opentlawpy/
├── src/
│   ├── whatsapp/
│   │   ├── __init__.py
│   │   ├── greenapi_client.py      # Green API wrapper
│   │   ├── greenapi_poller.py      # Polling service
│   │   └── models.py               # Data models
│   │
│   ├── activities/
│   │   └── whatsapp_greenapi.py    # Send message activity
│   │
│   ├── workflows/
│   │   └── agent_workflow.py       # (existing)
│   │
│   └── worker/
│       └── worker.py               # (existing)
│
├── config/
│   └── greenapi.yaml               # Green API configuration
│
├── docker-compose.yml
├── .env
└── requirements.txt
```

---

### Implementation: Green API Client

**File:** `src/whatsapp/greenapi_client.py`

```python
"""Green API WhatsApp client wrapper."""
from whatsapp_api_client_python import API
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class GreenAPIClient:
    """
    Wrapper around Green API Python library.
    Handles sending and receiving WhatsApp messages.
    """

    def __init__(self, instance_id: str, api_token: str):
        """
        Initialize Green API client.

        Args:
            instance_id: Green API instance ID
            api_token: Green API authentication token
        """
        self.instance_id = instance_id
        self.api_token = api_token

        self.greenapi = API.GreenAPI(
            idInstance=instance_id,
            apiTokenInstance=api_token
        )

        logger.info(f"Initialized Green API client for instance {instance_id}")

    async def send_message(self, to: str, text: str) -> Optional[str]:
        """
        Send text message.

        Args:
            to: Phone number (without +)
            text: Message text

        Returns:
            Message ID if successful, None otherwise
        """
        try:
            chat_id = self._format_chat_id(to)

            response = await self.greenapi.sending.sendMessageAsync(
                chatId=chat_id,
                message=text
            )

            message_id = response.data.get("idMessage")
            logger.info(f"Sent message to {to}: {message_id}")

            return message_id

        except Exception as e:
            logger.error(f"Failed to send message to {to}: {e}", exc_info=True)
            return None

    async def receive_notification(self) -> Optional[Dict]:
        """
        Receive next notification from queue (non-blocking).

        Returns:
            Notification dict if available, None if queue empty
        """
        try:
            response = await self.greenapi.receiving.receiveNotificationAsync()

            if response.data:
                return response.data

            return None

        except Exception as e:
            logger.error(f"Failed to receive notification: {e}", exc_info=True)
            return None

    async def delete_notification(self, receipt_id: int) -> bool:
        """
        Delete notification from queue (confirm processing).

        Args:
            receipt_id: Receipt ID from notification

        Returns:
            True if successful
        """
        try:
            await self.greenapi.receiving.deleteNotificationAsync(receipt_id)
            return True

        except Exception as e:
            logger.error(f"Failed to delete notification {receipt_id}: {e}")
            return False

    async def send_image(self, to: str, image_url: str, caption: Optional[str] = None) -> Optional[str]:
        """Send image message."""
        try:
            chat_id = self._format_chat_id(to)

            response = await self.greenapi.sending.sendFileByUrlAsync(
                chatId=chat_id,
                urlFile=image_url,
                fileName="image.jpg",
                caption=caption or ""
            )

            return response.data.get("idMessage")

        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            return None

    async def send_document(self, to: str, document_url: str, filename: str) -> Optional[str]:
        """Send document message."""
        try:
            chat_id = self._format_chat_id(to)

            response = await self.greenapi.sending.sendFileByUrlAsync(
                chatId=chat_id,
                urlFile=document_url,
                fileName=filename
            )

            return response.data.get("idMessage")

        except Exception as e:
            logger.error(f"Failed to send document: {e}")
            return None

    def _format_chat_id(self, phone: str) -> str:
        """
        Format phone number to WhatsApp chat ID.

        Args:
            phone: Phone number (digits only, no +)

        Returns:
            Chat ID in format: 1234567890@c.us
        """
        # Remove any non-digit characters
        clean_phone = "".join(filter(str.isdigit, phone))
        return f"{clean_phone}@c.us"
```

---

### Implementation: Message Models

**File:** `src/whatsapp/models.py`

```python
"""WhatsApp message models for Green API."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WhatsAppMessage:
    """Incoming WhatsApp message."""
    from_number: str          # Phone number (cleaned)
    text: str                 # Message text
    timestamp: datetime       # Message timestamp
    message_id: str           # Green API message ID
    sender_name: Optional[str] = None
    is_group: bool = False
    group_id: Optional[str] = None

    @classmethod
    def from_greenapi_notification(cls, notification: dict) -> Optional['WhatsAppMessage']:
        """
        Parse Green API notification into WhatsAppMessage.

        Args:
            notification: Raw notification from Green API

        Returns:
            WhatsAppMessage if valid, None otherwise
        """
        webhook_type = notification.get("typeWebhook")

        # Only process incoming messages
        if webhook_type != "incomingMessageReceived":
            return None

        body = notification.get("body", {})
        message_data = body.get("messageData", {})
        sender_data = body.get("senderData", {})

        # Extract sender info
        sender = sender_data.get("sender", "")
        from_number = sender.replace("@c.us", "").replace("@g.us", "")
        sender_name = sender_data.get("senderName")

        # Check if group message
        is_group = "@g.us" in sender
        group_id = sender if is_group else None

        # Extract message text
        text = None
        if "textMessageData" in message_data:
            text = message_data["textMessageData"].get("textMessage", "")
        elif "extendedTextMessageData" in message_data:
            text = message_data["extendedTextMessageData"].get("text", "")

        if not text:
            return None  # Skip non-text messages

        # Get timestamp
        timestamp_unix = body.get("timestamp", 0)
        timestamp = datetime.fromtimestamp(timestamp_unix)

        # Get message ID
        message_id = notification.get("idMessage", "")

        return cls(
            from_number=from_number,
            text=text,
            timestamp=timestamp,
            message_id=message_id,
            sender_name=sender_name,
            is_group=is_group,
            group_id=group_id,
        )
```

---

### Implementation: Polling Service

**File:** `src/whatsapp/greenapi_poller.py`

```python
"""
Green API polling service.
Continuously polls for WhatsApp messages and routes to Temporal.
"""
import asyncio
from temporalio.client import Client
import os
import logging
from typing import Optional

from .greenapi_client import GreenAPIClient
from .models import WhatsAppMessage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GreenAPIPoller:
    """Polls Green API for messages and routes to Temporal workflows."""

    def __init__(
        self,
        greenapi_client: GreenAPIClient,
        temporal_client: Client,
        poll_interval: int = 5,
    ):
        """
        Initialize poller.

        Args:
            greenapi_client: Green API client instance
            temporal_client: Temporal client
            poll_interval: Polling interval in seconds (default: 5)
        """
        self.greenapi = greenapi_client
        self.temporal = temporal_client
        self.poll_interval = poll_interval
        self.running = False

        logger.info(f"Initialized poller with {poll_interval}s interval")

    async def start(self):
        """Start polling loop."""
        self.running = True
        logger.info("Starting Green API polling loop...")

        while self.running:
            try:
                await self._poll_once()

            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def stop(self):
        """Stop polling loop."""
        logger.info("Stopping poller...")
        self.running = False

    async def _poll_once(self):
        """Execute one polling cycle."""
        # Get next notification from queue
        notification = await self.greenapi.receive_notification()

        if not notification:
            # Queue empty, wait before next poll
            await asyncio.sleep(self.poll_interval)
            return

        receipt_id = notification.get("receiptId")

        try:
            # Parse notification
            message = WhatsAppMessage.from_greenapi_notification(notification)

            if message:
                # Route to workflow
                await self._route_message(message)
            else:
                logger.debug(f"Skipped non-text notification: {notification.get('typeWebhook')}")

            # Confirm processing (remove from queue)
            await self.greenapi.delete_notification(receipt_id)

        except Exception as e:
            logger.error(f"Failed to process notification {receipt_id}: {e}", exc_info=True)
            # Don't delete notification on error - will retry

    async def _route_message(self, message: WhatsAppMessage):
        """
        Route message to appropriate Temporal workflow.

        Args:
            message: Parsed WhatsApp message
        """
        # Determine workflow ID (one per phone number)
        workflow_id = f"agent-whatsapp-{message.from_number}"

        logger.info(
            f"Routing message from {message.from_number} to workflow {workflow_id}"
        )

        try:
            # Try to get existing workflow
            handle = self.temporal.get_workflow_handle(workflow_id)

            try:
                await handle.describe()
                logger.debug(f"Workflow {workflow_id} exists")
            except:
                # Workflow doesn't exist, start it
                await self._start_workflow(workflow_id, message.from_number)
                handle = self.temporal.get_workflow_handle(workflow_id)

            # Send message as signal
            await handle.signal(
                "new_message",
                message.from_number,
                message.text
            )

            logger.info(f"Sent signal to workflow {workflow_id}")

        except Exception as e:
            logger.error(f"Failed to route message to workflow: {e}", exc_info=True)
            raise

    async def _start_workflow(self, workflow_id: str, phone_number: str):
        """
        Start new agent workflow for user.

        Args:
            workflow_id: Workflow ID
            phone_number: User's phone number
        """
        from src.workflows.agent_workflow import AgentWorkflow
        from src.models.state import WorkflowConfig

        logger.info(f"Starting new workflow {workflow_id} for {phone_number}")

        config = WorkflowConfig(
            max_duration_minutes=60,
            heartbeat_interval_minutes=5,
            system_prompt=f"You are a helpful AI assistant on WhatsApp. "
                         f"User's phone: {phone_number}",
        )

        await self.temporal.start_workflow(
            AgentWorkflow.run,
            config,
            id=workflow_id,
            task_queue="agent-workflows",
        )

        logger.info(f"Workflow {workflow_id} started successfully")


async def main():
    """Main entry point for poller service."""
    # Load configuration
    instance_id = os.getenv("GREEN_API_INSTANCE_ID")
    api_token = os.getenv("GREEN_API_TOKEN")
    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    poll_interval = int(os.getenv("POLL_INTERVAL", "5"))

    if not instance_id or not api_token:
        logger.error("GREEN_API_INSTANCE_ID and GREEN_API_TOKEN must be set")
        return

    # Initialize clients
    logger.info("Connecting to Temporal...")
    temporal_client = await Client.connect(temporal_address)

    logger.info("Initializing Green API client...")
    greenapi_client = GreenAPIClient(instance_id, api_token)

    # Start poller
    poller = GreenAPIPoller(
        greenapi_client=greenapi_client,
        temporal_client=temporal_client,
        poll_interval=poll_interval,
    )

    try:
        await poller.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt, stopping...")
        await poller.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

---

### Implementation: Send Activity

**File:** `src/activities/whatsapp_greenapi.py`

```python
"""WhatsApp sending activity using Green API."""
from temporalio import activity
from dataclasses import dataclass
from typing import Optional
import os
import logging

from src.whatsapp.greenapi_client import GreenAPIClient

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppSendInput:
    """Input for sending WhatsApp message."""
    to: str              # Phone number (digits only, no +)
    text: str            # Message text
    image_url: Optional[str] = None
    document_url: Optional[str] = None
    document_filename: Optional[str] = None


@dataclass
class WhatsAppSendOutput:
    """Output from sending WhatsApp message."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


# Global client instance (initialized once per worker)
_greenapi_client: Optional[GreenAPIClient] = None


def get_greenapi_client() -> GreenAPIClient:
    """Get or create Green API client instance."""
    global _greenapi_client

    if _greenapi_client is None:
        instance_id = os.getenv("GREEN_API_INSTANCE_ID")
        api_token = os.getenv("GREEN_API_TOKEN")

        if not instance_id or not api_token:
            raise RuntimeError("GREEN_API_INSTANCE_ID and GREEN_API_TOKEN must be set")

        _greenapi_client = GreenAPIClient(instance_id, api_token)

    return _greenapi_client


@activity.defn
async def send_whatsapp_message(input: WhatsAppSendInput) -> WhatsAppSendOutput:
    """
    Send WhatsApp message via Green API.

    Args:
        input: Message details

    Returns:
        Send result with message ID or error
    """
    activity.logger.info(f"Sending WhatsApp to {input.to}")

    try:
        client = get_greenapi_client()

        # Send based on message type
        if input.image_url:
            # Send image with optional caption
            message_id = await client.send_image(
                to=input.to,
                image_url=input.image_url,
                caption=input.text if input.text else None
            )
        elif input.document_url:
            # Send document
            message_id = await client.send_document(
                to=input.to,
                document_url=input.document_url,
                filename=input.document_filename or "document.pdf"
            )
        else:
            # Send text message
            message_id = await client.send_message(
                to=input.to,
                text=input.text
            )

        if message_id:
            activity.logger.info(f"Message sent successfully: {message_id}")
            return WhatsAppSendOutput(
                success=True,
                message_id=message_id
            )
        else:
            activity.logger.error("Failed to send message (no message ID)")
            return WhatsAppSendOutput(
                success=False,
                error="No message ID returned"
            )

    except Exception as e:
        activity.logger.error(f"Failed to send WhatsApp: {e}", exc_info=True)
        return WhatsAppSendOutput(
            success=False,
            error=str(e)
        )
```

---

## Temporal Integration

### Update Agent Workflow

Add WhatsApp response handling to your agent workflow:

```python
# src/workflows/agent_workflow.py

from src.activities.whatsapp_greenapi import (
    send_whatsapp_message,
    WhatsAppSendInput,
)

@workflow.defn
class AgentWorkflow:
    # ... existing code ...

    async def _process_messages(self):
        """Process pending messages."""
        while self.pending_messages:
            user_msg = self.pending_messages.pop(0)
            sender = user_msg.metadata.get("sender", "")

            # Add to conversation
            self.state.conversation.messages.append(user_msg)

            # Call LLM
            llm_response = await self._call_llm()

            # Add response to conversation
            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content=llm_response.response_text
            )
            self.state.conversation.messages.append(assistant_msg)

            # Send response via WhatsApp
            if sender:
                await self._send_whatsapp(sender, llm_response.response_text)

    async def _send_whatsapp(self, to: str, text: str):
        """Send WhatsApp response."""
        result = await workflow.execute_activity(
            send_whatsapp_message,
            WhatsAppSendInput(
                to=to,
                text=text
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            )
        )

        if not result.success:
            workflow.logger.error(f"Failed to send WhatsApp: {result.error}")
```

---

## Deployment

### Environment Variables

**File:** `.env`

```bash
# Green API Configuration
GREEN_API_INSTANCE_ID=1101000001
GREEN_API_TOKEN=d75b3a66374942c5b3c019c698abc2067e151558acbd412345

# Polling Configuration
POLL_INTERVAL=5  # Seconds between polls

# Temporal
TEMPORAL_ADDRESS=localhost:7233

# LLM
OPENAI_API_KEY=sk-...
```

---

### Docker Compose

**File:** `docker-compose.yml`

```yaml
version: '3.8'

services:
  # Temporal Server
  temporal:
    image: temporalio/auto-setup:latest
    ports:
      - "7233:7233"
      - "8233:8233"
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgresql
    depends_on:
      - postgresql

  # PostgreSQL
  postgresql:
    image: postgres:15
    environment:
      - POSTGRES_USER=temporal
      - POSTGRES_PASSWORD=temporal
    volumes:
      - temporal-postgres-data:/var/lib/postgresql/data

  # Green API Poller Service
  greenapi-poller:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - GREEN_API_INSTANCE_ID=${GREEN_API_INSTANCE_ID}
      - GREEN_API_TOKEN=${GREEN_API_TOKEN}
      - TEMPORAL_ADDRESS=temporal:7233
      - POLL_INTERVAL=${POLL_INTERVAL:-5}
    depends_on:
      - temporal
    command: python -m src.whatsapp.greenapi_poller
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # Temporal Worker
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - GREEN_API_INSTANCE_ID=${GREEN_API_INSTANCE_ID}
      - GREEN_API_TOKEN=${GREEN_API_TOKEN}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./state:/app/state
      - ./workspace:/app/workspace
    depends_on:
      - temporal
    command: python -m src.worker.worker
    restart: unless-stopped

volumes:
  temporal-postgres-data:
```

---

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY config/ ./config/

# Create directories
RUN mkdir -p /app/state /app/workspace

# Default command (override in docker-compose)
CMD ["python", "-m", "src.worker.worker"]
```

---

### Requirements.txt

```txt
# Temporal
temporalio>=1.5.0

# Green API
whatsapp-api-client-python>=0.0.53

# LLM Providers
openai>=1.0.0
anthropic>=0.18.0

# Web Framework
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.5.0

# Utilities
pyyaml>=6.0
python-dotenv>=1.0.0
httpx>=0.26.0
aiofiles>=23.2.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_greenapi_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.whatsapp.greenapi_client import GreenAPIClient


@pytest.mark.asyncio
async def test_send_message_success(monkeypatch):
    """Test successful message sending."""
    # Mock Green API response
    mock_response = MagicMock()
    mock_response.data = {"idMessage": "ABC123"}

    mock_greenapi = MagicMock()
    mock_greenapi.sending.sendMessageAsync = AsyncMock(return_value=mock_response)

    client = GreenAPIClient("instance", "token")
    client.greenapi = mock_greenapi

    # Send message
    message_id = await client.send_message("1234567890", "Hello")

    assert message_id == "ABC123"
    mock_greenapi.sending.sendMessageAsync.assert_called_once()


@pytest.mark.asyncio
async def test_receive_notification():
    """Test receiving notification from queue."""
    mock_response = MagicMock()
    mock_response.data = {
        "receiptId": 1,
        "typeWebhook": "incomingMessageReceived",
        "body": {
            "messageData": {"textMessageData": {"textMessage": "Hello"}},
            "senderData": {"sender": "1234567890@c.us"}
        }
    }

    mock_greenapi = MagicMock()
    mock_greenapi.receiving.receiveNotificationAsync = AsyncMock(
        return_value=mock_response
    )

    client = GreenAPIClient("instance", "token")
    client.greenapi = mock_greenapi

    notification = await client.receive_notification()

    assert notification is not None
    assert notification["receiptId"] == 1
```

### Integration Tests

```python
# tests/test_integration_greenapi.py
import pytest
import asyncio
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.workflows.agent_workflow import AgentWorkflow
from src.activities.whatsapp_greenapi import send_whatsapp_message


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_whatsapp_flow():
    """Test complete flow: message → workflow → response."""
    # This requires real Green API credentials
    # Set GREEN_API_INSTANCE_ID and GREEN_API_TOKEN in env

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[AgentWorkflow],
            activities=[send_whatsapp_message]
        ):
            # Start workflow
            handle = await env.client.start_workflow(
                AgentWorkflow.run,
                # ... config
                id="test-agent",
                task_queue="test-queue"
            )

            # Send test message
            await handle.signal("new_message", "1234567890", "Hello")

            # Wait for processing
            await asyncio.sleep(2)

            # Verify state
            state = await handle.query("get_state")
            assert state["message_count"] > 0
```

### Manual Testing

```bash
# 1. Start services
docker-compose up

# 2. Check poller logs
docker-compose logs -f greenapi-poller

# 3. Send test message from your phone to the linked WhatsApp number

# 4. Watch logs for:
#    - Message received
#    - Workflow signal sent
#    - LLM processing
#    - Response sent

# 5. Verify response received on your phone
```

---

## Monitoring & Operations

### Health Checks

```python
# src/whatsapp/health.py
"""Health check endpoint for poller service."""
from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "greenapi-poller",
        "instance_id": os.getenv("GREEN_API_INSTANCE_ID"),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

Add to docker-compose.yml:

```yaml
greenapi-poller:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### Logging

```python
# Configure structured logging
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.root.addHandler(handler)
```

### Metrics (Optional)

```python
from prometheus_client import Counter, Histogram

messages_received = Counter(
    'whatsapp_messages_received_total',
    'Total WhatsApp messages received'
)

messages_sent = Counter(
    'whatsapp_messages_sent_total',
    'Total WhatsApp messages sent'
)

poll_duration = Histogram(
    'whatsapp_poll_duration_seconds',
    'Time to poll for messages'
)
```

---

## Cost Analysis

### Green API Pricing (2026 Estimates)

**Free Developer Tier:**
- Limited messages per month
- Good for testing
- All features available

**Business Plans:**
- **Starter:** ~$20/month
  - 1,000 messages/month included
  - Additional: ~$0.02/message

- **Professional:** ~$50/month
  - 5,000 messages/month
  - Priority support

- **Enterprise:** Custom pricing
  - Unlimited messages
  - SLA guarantees

### Cost Comparison

| Volume | Green API | WhatsApp Cloud API | Baileys |
|--------|-----------|-------------------|---------|
| 1K msgs/month | $20 | $5-$10 | Free |
| 5K msgs/month | $50 | $25-$50 | Free |
| 20K msgs/month | $150-200 | $100-$500 | Free |

**Additional Costs:**
- Temporal Cloud: ~$50+/month (or self-hosted free)
- Server/VPS: ~$5-20/month (if not using cloud)
- LLM API: Variable (based on usage)

---

## Pros & Cons

### Advantages ✅

1. **No Public URL Required**
   - Polling-based architecture
   - Run on private network
   - No ngrok, no port forwarding

2. **Production Ready**
   - Managed service (no maintenance)
   - 24-hour message queue (resilient)
   - High uptime guarantee

3. **Easy Integration**
   - Official Python library
   - Clean API design
   - Good documentation

4. **Reliable**
   - No session breakage
   - No WhatsApp Web protocol changes
   - Professional support

5. **Feature Rich**
   - Send text, images, documents
   - Group messages
   - Message tracking

### Disadvantages ❌

1. **Cost**
   - Not free (starts at $20/month)
   - Per-message charges on higher volumes
   - More expensive than self-hosted

2. **Third-Party Dependency**
   - Not official Meta API
   - Vendor lock-in
   - Service availability risk

3. **Polling Overhead**
   - Slight delay (5 second intervals)
   - More API calls than webhooks
   - Battery/resource usage on mobile

4. **Limited Control**
   - Can't customize low-level behavior
   - Dependent on Green API features
   - API rate limits

### Risk Mitigation

**Service Outage:**
- 24-hour queue retains messages
- Monitor health endpoint
- Alert on prolonged failures

**Vendor Lock-in:**
- Abstract Green API behind interface
- Easy to swap for different provider
- See migration path below

**Cost Overruns:**
- Set alerts for usage thresholds
- Rate limit per user
- Archive old conversations

---

## Migration Path

### If You Want to Switch Later

The architecture is designed for easy migration:

#### To WhatsApp Cloud API (PyWa)

```python
# 1. Replace poller with webhook handler
# 2. Swap GreenAPIClient with PyWa client
# 3. Change send_whatsapp_message activity implementation
# 4. Deploy with public URL (Cloudflare Tunnel)
```

**Effort:** ~4 hours

#### To Baileys (Free)

```python
# 1. Deploy Baileys bridge (Node.js)
# 2. Replace GreenAPIClient with BaileysClient (HTTP calls)
# 3. No other changes needed!
```

**Effort:** ~2 hours

#### To Twilio

```python
# 1. Get Twilio account
# 2. Replace GreenAPIClient with Twilio client
# 3. Add webhook handler instead of poller
# 4. Deploy with public URL
```

**Effort:** ~3 hours

### Code Abstraction for Easy Migration

```python
# src/whatsapp/interface.py
from abc import ABC, abstractmethod

class WhatsAppProvider(ABC):
    """Abstract WhatsApp provider interface."""

    @abstractmethod
    async def send_message(self, to: str, text: str) -> Optional[str]:
        """Send message."""
        pass

    @abstractmethod
    async def receive_messages(self) -> List[WhatsAppMessage]:
        """Receive new messages."""
        pass


# Then implement for each provider
class GreenAPIProvider(WhatsAppProvider):
    # ... Green API implementation

class BaileysProvider(WhatsAppProvider):
    # ... Baileys implementation

class PyWaProvider(WhatsAppProvider):
    # ... PyWa implementation
```

**Benefits:**
- Swap providers by changing one line
- Test multiple providers easily
- Gradual migration possible

---

## Deployment Checklist

### Pre-Deployment

- [ ] Green API account created
- [ ] Instance ID and token obtained
- [ ] WhatsApp number linked (QR scanned)
- [ ] Environment variables set
- [ ] Temporal server running
- [ ] Docker Compose tested locally

### Deployment

- [ ] Deploy to production server
- [ ] Verify poller starts successfully
- [ ] Send test message from phone
- [ ] Verify workflow receives signal
- [ ] Verify response received
- [ ] Check logs for errors

### Post-Deployment

- [ ] Set up monitoring alerts
- [ ] Configure log aggregation
- [ ] Test failure scenarios
- [ ] Document runbook procedures
- [ ] Schedule cost review

---

## Troubleshooting

### Poller Not Receiving Messages

**Check:**
1. Green API instance status (console)
2. Environment variables set correctly
3. Poller logs for errors
4. Network connectivity to Green API

**Fix:**
```bash
# Restart poller
docker-compose restart greenapi-poller

# Check logs
docker-compose logs greenapi-poller
```

### Messages Not Sending

**Check:**
1. Activity logs for errors
2. Green API instance status
3. Phone number format (digits only, no +)
4. API token validity

### High Latency

**Causes:**
- Long polling interval (increase frequency)
- Green API server latency
- Network issues

**Optimization:**
```python
# Reduce poll interval
POLL_INTERVAL=2  # 2 seconds instead of 5
```

---

## Conclusion

Green API provides a **production-ready, reliable** WhatsApp integration that doesn't require a public URL. While it costs money (~$20/month), the trade-off is **stability and simplicity**.

**Recommended For:**
- Production deployments
- Business use cases
- When reliability > cost
- When you want support

**Not Recommended For:**
- Hobby projects (use Baileys)
- High-volume (>20K msgs/month) - expensive
- When you need 100% free solution

**Next Steps:**
1. Sign up for Green API free tier
2. Test with sample integration
3. Evaluate for 1 week
4. Decide: Green API vs Baileys vs Cloud API

---

## Additional Resources

- [Green API Documentation](https://green-api.com/en/docs/)
- [Python Library GitHub](https://github.com/green-api/whatsapp-api-client-python)
- [Green API Console](https://console.green-api.com/)
- [Pricing Page](https://green-api.com/en/pricing.html)
- [Support](https://green-api.com/en/support/)

---

**Plan Version:** 1.0
**Last Updated:** 2026-02-28
**Status:** Ready for Implementation
