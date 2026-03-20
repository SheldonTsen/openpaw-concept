# WhatsApp Integration with PyWa (Python)

## Overview

This document describes WhatsApp integration using **PyWa** (https://pywa.readthedocs.io/), a Python library for WhatsApp Business API and Cloud API. This keeps the entire stack in Python, simplifying development and deployment.

---

## PyWa Overview

**PyWa** supports two modes:
1. **WhatsApp Cloud API** (recommended for production) - Official Meta API, requires approval
2. **WhatsApp Business API** (on-premises) - Self-hosted Business API

For this integration, we'll use the **Cloud API** approach, which is easier to set up and officially supported.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    WhatsApp Cloud API                        │
│                     (Meta/Facebook)                          │
└──────────────┬──────────────────────────────┬────────────────┘
               │                              │
       (Incoming webhooks)            (Outgoing API calls)
               │                              │
               ▼                              ▲
┌──────────────────────────────────────────────────────────────┐
│                  WhatsApp Handler Service                    │
│  - FastAPI app with PyWa integration                        │
│  - Receives webhooks from Meta                              │
│  - Sends signals to Temporal workflows                      │
│  - Exposes activity for sending messages                    │
└──────────────┬──────────────────────────────┬────────────────┘
               │                              │
          (Signals)                     (Activities)
               │                              │
               ▼                              ▲
┌──────────────────────────────────────────────────────────────┐
│              Agent Workflows (Temporal)                      │
│  - Receive messages via signals                             │
│  - Process with LLM                                         │
│  - Execute tools                                            │
│  - Send responses via WhatsApp activity                     │
└──────────────────────────────────────────────────────────────┘
```

**Simplified Architecture** (since it's all Python):
- WhatsApp handler can be part of the Gateway service
- No separate Node.js service needed
- PyWa handles all WhatsApp communication

---

## Setup Requirements

### 1. WhatsApp Business Account Setup

1. **Create Meta Business Account**: https://business.facebook.com/
2. **Create WhatsApp Business App**: https://developers.facebook.com/apps
3. **Get credentials**:
   - Phone Number ID
   - WhatsApp Business Account ID
   - Access Token
   - App Secret (for webhook verification)

### 2. Webhook Configuration

Meta will send incoming messages to your webhook URL:
- Must be HTTPS (use ngrok for local dev)
- Must verify with challenge token
- Must respond within 20 seconds

---

## Implementation

### File Structure

```
src/
├── whatsapp/
│   ├── __init__.py
│   ├── client.py           # PyWa client wrapper
│   ├── webhook.py          # FastAPI webhook handlers
│   ├── activities.py       # Temporal activities for sending
│   └── models.py           # Data models
│
├── gateway/
│   ├── app.py              # Main FastAPI app (includes WhatsApp)
│   └── routes.py
│
├── workflows/
│   └── agent_workflow.py
│
└── activities/
    └── whatsapp_delivery.py
```

---

## Code Implementation

### 1. WhatsApp Client (whatsapp/client.py)

```python
"""WhatsApp client using PyWa."""
from pywa import WhatsApp
from pywa.types import Message, CallbackButton, Button
import os
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Wrapper around PyWa client."""

    def __init__(
        self,
        phone_id: str,
        token: str,
        server: Optional[str] = None,
        app_secret: Optional[str] = None,
        verify_token: Optional[str] = None,
        on_message: Optional[Callable] = None,
    ):
        """
        Initialize WhatsApp client.

        Args:
            phone_id: WhatsApp phone number ID from Meta
            token: Access token from Meta
            server: Server URL for webhooks (optional)
            app_secret: App secret for webhook verification
            verify_token: Token for webhook verification
            on_message: Callback for incoming messages
        """
        self.phone_id = phone_id
        self.token = token
        self.on_message_callback = on_message

        # Initialize PyWa client
        self.wa = WhatsApp(
            phone_id=phone_id,
            token=token,
            server=server,
            app_secret=app_secret,
            verify_token=verify_token,
        )

        # Register message handler if callback provided
        if on_message:
            self.wa.on_message(self._handle_message)

        logger.info(f"WhatsApp client initialized for phone ID: {phone_id}")

    def _handle_message(self, client: WhatsApp, msg: Message):
        """Internal message handler."""
        logger.info(f"Received message from {msg.from_user.wa_id}: {msg.text}")

        if self.on_message_callback:
            try:
                self.on_message_callback(msg)
            except Exception as e:
                logger.error(f"Error in message callback: {e}", exc_info=True)

    async def send_text(
        self,
        to: str,
        text: str,
        reply_to_message_id: Optional[str] = None,
    ) -> str:
        """
        Send text message.

        Args:
            to: Recipient phone number (with country code, no +)
            text: Message text
            reply_to_message_id: Optional message ID to reply to

        Returns:
            Message ID
        """
        try:
            result = self.wa.send_message(
                to=to,
                text=text,
                reply_to_message_id=reply_to_message_id,
            )
            logger.info(f"Sent message to {to}: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to send message to {to}: {e}", exc_info=True)
            raise

    async def send_image(
        self,
        to: str,
        image: str,
        caption: Optional[str] = None,
    ) -> str:
        """
        Send image message.

        Args:
            to: Recipient phone number
            image: Image URL or path
            caption: Optional caption

        Returns:
            Message ID
        """
        return self.wa.send_image(
            to=to,
            image=image,
            caption=caption,
        )

    async def send_document(
        self,
        to: str,
        document: str,
        filename: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> str:
        """Send document message."""
        return self.wa.send_document(
            to=to,
            document=document,
            filename=filename,
            caption=caption,
        )

    async def send_audio(
        self,
        to: str,
        audio: str,
    ) -> str:
        """Send audio message."""
        return self.wa.send_audio(
            to=to,
            audio=audio,
        )

    async def send_video(
        self,
        to: str,
        video: str,
        caption: Optional[str] = None,
    ) -> str:
        """Send video message."""
        return self.wa.send_video(
            to=to,
            video=video,
            caption=caption,
        )

    async def send_location(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
    ) -> str:
        """Send location message."""
        return self.wa.send_location(
            to=to,
            latitude=latitude,
            longitude=longitude,
            name=name,
            address=address,
        )

    async def send_buttons(
        self,
        to: str,
        text: str,
        buttons: list[Button],
    ) -> str:
        """
        Send message with buttons.

        Args:
            to: Recipient phone number
            text: Message text
            buttons: List of Button objects

        Returns:
            Message ID
        """
        return self.wa.send_message(
            to=to,
            text=text,
            buttons=buttons,
        )

    async def mark_as_read(self, message_id: str):
        """Mark message as read."""
        self.wa.mark_message_as_read(message_id)

    def get_webhook_handler(self):
        """Get FastAPI router for webhooks."""
        return self.wa.webhook_handler


# Global client instance
_whatsapp_client: Optional[WhatsAppClient] = None


def get_whatsapp_client() -> WhatsAppClient:
    """Get global WhatsApp client instance."""
    global _whatsapp_client
    if _whatsapp_client is None:
        raise RuntimeError("WhatsApp client not initialized. Call init_whatsapp_client first.")
    return _whatsapp_client


def init_whatsapp_client(
    phone_id: str,
    token: str,
    app_secret: str,
    verify_token: str,
    on_message: Optional[Callable] = None,
) -> WhatsAppClient:
    """Initialize global WhatsApp client."""
    global _whatsapp_client
    _whatsapp_client = WhatsAppClient(
        phone_id=phone_id,
        token=token,
        app_secret=app_secret,
        verify_token=verify_token,
        on_message=on_message,
    )
    return _whatsapp_client
```

---

### 2. Data Models (whatsapp/models.py)

```python
"""WhatsApp message models."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WhatsAppIncomingMessage:
    """Incoming WhatsApp message."""
    message_id: str
    from_number: str  # Phone number (no +)
    from_name: Optional[str]
    text: str
    timestamp: datetime
    is_reply: bool = False
    reply_to_message_id: Optional[str] = None


@dataclass
class WhatsAppOutgoingMessage:
    """Outgoing WhatsApp message."""
    to: str  # Phone number (no +)
    text: str
    reply_to_message_id: Optional[str] = None
```

---

### 3. Webhook Handler (whatsapp/webhook.py)

```python
"""WhatsApp webhook handlers."""
from fastapi import Request, HTTPException
from pywa.types import Message
from temporalio.client import Client
import logging
from .models import WhatsAppIncomingMessage
from .client import get_whatsapp_client

logger = logging.getLogger(__name__)


async def handle_whatsapp_message(
    msg: Message,
    temporal_client: Client,
):
    """
    Handle incoming WhatsApp message.
    Route to appropriate Temporal workflow.

    Args:
        msg: PyWa Message object
        temporal_client: Temporal client
    """
    # Extract message data
    incoming = WhatsAppIncomingMessage(
        message_id=msg.id,
        from_number=msg.from_user.wa_id,  # Phone number without +
        from_name=msg.from_user.name,
        text=msg.text or "",
        timestamp=msg.timestamp,
        is_reply=msg.reply_to_message is not None,
        reply_to_message_id=msg.reply_to_message.id if msg.reply_to_message else None,
    )

    logger.info(f"Incoming WhatsApp message: {incoming}")

    # Determine workflow ID
    # Option 1: One workflow per user
    workflow_id = f"agent-whatsapp-{incoming.from_number}"

    # Option 2: Single workflow for all WhatsApp
    # workflow_id = "agent-whatsapp-main"

    try:
        # Get or start workflow
        handle = temporal_client.get_workflow_handle(workflow_id)

        try:
            # Check if workflow exists
            await handle.describe()
        except Exception:
            # Workflow doesn't exist, start it
            from src.workflows.agent_workflow import AgentWorkflow
            from src.models.state import WorkflowConfig

            config = WorkflowConfig(
                max_duration_minutes=60,
                heartbeat_interval_minutes=5,
                system_prompt="You are a helpful AI assistant responding via WhatsApp.",
            )

            logger.info(f"Starting new workflow: {workflow_id}")
            handle = await temporal_client.start_workflow(
                AgentWorkflow.run,
                config,
                id=workflow_id,
                task_queue="agent-workflows",
            )

        # Send message as signal
        await handle.signal(
            "new_message",
            incoming.from_number,
            incoming.text,
        )

        # Mark as read
        wa_client = get_whatsapp_client()
        await wa_client.mark_as_read(incoming.message_id)

        logger.info(f"Message routed to workflow {workflow_id}")

    except Exception as e:
        logger.error(f"Failed to route WhatsApp message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 4. Gateway Integration (gateway/app.py)

```python
"""Main Gateway FastAPI application with WhatsApp integration."""
from fastapi import FastAPI, Request
from temporalio.client import Client
import os
import logging
from contextlib import asynccontextmanager

from src.whatsapp.client import init_whatsapp_client
from src.whatsapp.webhook import handle_whatsapp_message

logger = logging.getLogger(__name__)

# Global Temporal client
temporal_client: Client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global temporal_client

    # Initialize Temporal client
    logger.info("Connecting to Temporal...")
    temporal_client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    )

    # Initialize WhatsApp client
    logger.info("Initializing WhatsApp client...")
    wa_client = init_whatsapp_client(
        phone_id=os.getenv("WHATSAPP_PHONE_ID"),
        token=os.getenv("WHATSAPP_TOKEN"),
        app_secret=os.getenv("WHATSAPP_APP_SECRET"),
        verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN"),
        on_message=lambda msg: handle_whatsapp_message(msg, temporal_client),
    )

    logger.info("Gateway service started")

    yield

    # Cleanup
    logger.info("Shutting down gateway service")


# Create FastAPI app
app = FastAPI(
    title="openpaw Gateway",
    lifespan=lifespan,
)


# Mount PyWa webhook handler
# This handles webhook verification and incoming messages
from src.whatsapp.client import get_whatsapp_client

@app.get("/webhooks/whatsapp")
@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    WhatsApp webhook endpoint.
    Handles both verification (GET) and messages (POST).
    """
    wa_client = get_whatsapp_client()
    return await wa_client.wa.webhook_handler(request)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "temporal_connected": temporal_client is not None,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "openpaw-gateway",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
```

---

### 5. WhatsApp Delivery Activity (activities/whatsapp_delivery.py)

```python
"""WhatsApp message delivery activity."""
from temporalio import activity
from dataclasses import dataclass
from typing import Optional
import logging

from src.whatsapp.client import get_whatsapp_client

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppDeliveryInput:
    """Input for WhatsApp delivery activity."""
    to: str  # Phone number (without +)
    text: str
    reply_to_message_id: Optional[str] = None


@dataclass
class WhatsAppDeliveryOutput:
    """Output from WhatsApp delivery activity."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


@activity.defn
async def whatsapp_delivery_activity(
    input: WhatsAppDeliveryInput
) -> WhatsAppDeliveryOutput:
    """
    Send message via WhatsApp.

    Args:
        input: Delivery input with recipient and message

    Returns:
        Delivery result with message ID or error
    """
    activity.logger.info(f"Sending WhatsApp message to {input.to}")

    try:
        wa_client = get_whatsapp_client()

        message_id = await wa_client.send_text(
            to=input.to,
            text=input.text,
            reply_to_message_id=input.reply_to_message_id,
        )

        activity.logger.info(f"WhatsApp message sent: {message_id}")

        return WhatsAppDeliveryOutput(
            success=True,
            message_id=message_id,
        )

    except Exception as e:
        activity.logger.error(f"Failed to send WhatsApp message: {e}", exc_info=True)

        return WhatsAppDeliveryOutput(
            success=False,
            error=str(e),
        )
```

---

### 6. Update Agent Workflow

Add WhatsApp response sending to agent workflow:

```python
# In agent_workflow.py

from src.activities.whatsapp_delivery import (
    whatsapp_delivery_activity,
    WhatsAppDeliveryInput,
)

@workflow.defn
class AgentWorkflow:
    # ... existing code ...

    async def _process_messages(self):
        """Process all pending messages."""
        while self.pending_messages:
            user_msg = self.pending_messages.pop(0)
            sender = user_msg.metadata.get("sender", "")

            self.state.conversation.messages.append(user_msg)

            # Call LLM
            llm_response = await self._call_llm()

            # Execute tools if needed
            # ... (existing tool execution logic)

            # Add assistant response to conversation
            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content=llm_response.response_text
            )
            self.state.conversation.messages.append(assistant_msg)

            # Send response via WhatsApp
            if sender:
                await self._send_whatsapp_response(
                    sender,
                    llm_response.response_text
                )

    async def _send_whatsapp_response(self, to: str, text: str):
        """Send response via WhatsApp."""
        result = await workflow.execute_activity(
            whatsapp_delivery_activity,
            WhatsAppDeliveryInput(
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

## Configuration

### Environment Variables (.env)

```bash
# Temporal
TEMPORAL_ADDRESS=localhost:7233

# WhatsApp (from Meta Business Account)
WHATSAPP_PHONE_ID=123456789012345
WHATSAPP_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_VERIFY_TOKEN=my_secure_verify_token_123

# Gateway
PORT=8000
LOG_LEVEL=INFO

# LLM
OPENAI_API_KEY=sk-...
```

---

### Docker Compose

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

  # PostgreSQL for Temporal
  postgresql:
    image: postgres:15
    environment:
      - POSTGRES_USER=temporal
      - POSTGRES_PASSWORD=temporal
    volumes:
      - temporal-postgres-data:/var/lib/postgresql/data

  # Worker
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - WHATSAPP_PHONE_ID=${WHATSAPP_PHONE_ID}
      - WHATSAPP_TOKEN=${WHATSAPP_TOKEN}
    volumes:
      - ./state:/app/state
      - ./workspace:/app/workspace
    depends_on:
      - temporal
    command: python -m src.worker.worker

  # Gateway (includes WhatsApp webhook handler)
  gateway:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - WHATSAPP_PHONE_ID=${WHATSAPP_PHONE_ID}
      - WHATSAPP_TOKEN=${WHATSAPP_TOKEN}
      - WHATSAPP_APP_SECRET=${WHATSAPP_APP_SECRET}
      - WHATSAPP_VERIFY_TOKEN=${WHATSAPP_VERIFY_TOKEN}
    depends_on:
      - temporal
    command: python -m src.gateway.app

volumes:
  temporal-postgres-data:
```

---

## Setup Steps

### 1. Get WhatsApp Cloud API Credentials

1. Go to https://developers.facebook.com/apps
2. Create new app → Business → WhatsApp
3. Add WhatsApp product
4. Get test phone number or add your own
5. Copy:
   - **Phone Number ID** (from "API Setup")
   - **Access Token** (temporary or permanent)
   - **App Secret** (from Settings → Basic)
6. Generate a **Verify Token** (any random string you create)

### 2. Configure Webhook

In Meta App Dashboard:
1. Go to WhatsApp → Configuration
2. Set webhook URL: `https://your-domain.com/webhooks/whatsapp`
3. Set verify token (same as `WHATSAPP_VERIFY_TOKEN`)
4. Subscribe to: `messages`

For local development, use **ngrok**:
```bash
ngrok http 8000
# Use the ngrok URL: https://abc123.ngrok.io/webhooks/whatsapp
```

### 3. Start Services

```bash
# Set environment variables
export WHATSAPP_PHONE_ID=...
export WHATSAPP_TOKEN=...
export WHATSAPP_APP_SECRET=...
export WHATSAPP_VERIFY_TOKEN=...

# Start all services
docker-compose up
```

### 4. Test

Send a WhatsApp message to your business number:
1. Message appears in logs
2. Workflow starts automatically
3. LLM processes message
4. Response sent back via WhatsApp

---

## Advanced Features

### 1. Interactive Buttons

```python
from pywa import Button

# In your workflow or activity
buttons = [
    Button(title="Option 1", callback_data="opt1"),
    Button(title="Option 2", callback_data="opt2"),
]

await wa_client.send_buttons(
    to=user_number,
    text="Choose an option:",
    buttons=buttons,
)
```

Handle button callbacks:
```python
@wa_client.on_callback_button
def handle_button(client: WhatsApp, btn):
    # btn.data contains the callback_data
    logger.info(f"Button pressed: {btn.data}")
```

### 2. Media Messages

```python
# Send image
await wa_client.send_image(
    to=user_number,
    image="https://example.com/image.jpg",
    caption="Check this out!"
)

# Send document
await wa_client.send_document(
    to=user_number,
    document="https://example.com/report.pdf",
    filename="Report.pdf",
    caption="Your report is ready"
)
```

### 3. Template Messages

For customer-initiated messages (24-hour window) vs business-initiated:

```python
# Template messages (for notifications outside 24h window)
wa_client.send_template(
    to=user_number,
    template_name="appointment_reminder",
    template_language="en",
    components=[...],
)
```

### 4. Message Status Tracking

```python
@wa_client.on_message_status
def handle_status(client: WhatsApp, status):
    """Track message delivery/read status."""
    logger.info(f"Message {status.id} status: {status.status}")
    # Status can be: sent, delivered, read, failed
```

---

## Security & Best Practices

### 1. Webhook Verification

PyWa automatically verifies webhook signatures using `app_secret`. Always provide this in production.

### 2. Rate Limiting

WhatsApp Cloud API has rate limits:
- **Business Conversations**: 1000/day (can be increased)
- **Messaging Throughput**: 80 messages/second

Implement rate limiting:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/webhooks/whatsapp")
@limiter.limit("100/minute")
async def whatsapp_webhook(request: Request):
    # ...
```

### 3. Message Templates

For marketing/notifications, you must use approved templates:
1. Create template in Meta Business Manager
2. Wait for approval
3. Use template name in API calls

### 4. Data Privacy

- Don't log full message content in production
- Encrypt sensitive data in state.md
- Follow GDPR/privacy regulations

---

## Troubleshooting

### Webhook Not Receiving Messages

**Check**:
1. URL is publicly accessible (HTTPS)
2. Verify token matches
3. Webhook subscriptions include `messages`
4. Check Meta App Dashboard → WhatsApp → Webhooks → Test

### Messages Not Sending

**Check**:
1. Access token is valid (check expiry)
2. Phone number format (no `+`, just digits)
3. Rate limits not exceeded
4. Message is within 24-hour customer window (or use template)

### Authentication Errors

**Check**:
1. `WHATSAPP_TOKEN` is correct
2. Token has required permissions (`whatsapp_business_messaging`)
3. Phone number ID matches your app

---

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.activities.whatsapp_delivery import (
    whatsapp_delivery_activity,
    WhatsAppDeliveryInput,
)


@pytest.mark.asyncio
async def test_whatsapp_delivery_success(monkeypatch):
    # Mock WhatsApp client
    mock_client = AsyncMock()
    mock_client.send_text.return_value = "wamid.abc123"

    def mock_get_client():
        return mock_client

    monkeypatch.setattr(
        "src.activities.whatsapp_delivery.get_whatsapp_client",
        mock_get_client,
    )

    # Test activity
    result = await whatsapp_delivery_activity(
        WhatsAppDeliveryInput(
            to="1234567890",
            text="Test message"
        )
    )

    assert result.success
    assert result.message_id == "wamid.abc123"
    mock_client.send_text.assert_called_once_with(
        to="1234567890",
        text="Test message",
        reply_to_message_id=None,
    )
```

### Integration Test

```python
@pytest.mark.integration
async def test_whatsapp_end_to_end():
    """Test full flow: webhook → workflow → response."""
    # Requires real WhatsApp credentials
    # Send test message via WhatsApp Test Phone Number
    # Verify workflow receives signal
    # Verify response is sent
    pass
```

---

## Production Deployment

### 1. Get Production Access Token

Test tokens expire after 24 hours. For production:
1. Generate **System User** token
2. Never expires (until revoked)
3. Store securely (AWS Secrets Manager, etc.)

### 2. Increase Rate Limits

Request rate limit increase from Meta:
1. Business Manager → Business Settings
2. WhatsApp Accounts → select account
3. Request limit increase (provide business justification)

### 3. Monitoring

Add health checks and metrics:

```python
from prometheus_client import Counter, Histogram

whatsapp_messages_received = Counter(
    'whatsapp_messages_received_total',
    'Total WhatsApp messages received'
)

whatsapp_messages_sent = Counter(
    'whatsapp_messages_sent_total',
    'Total WhatsApp messages sent'
)

whatsapp_send_duration = Histogram(
    'whatsapp_send_duration_seconds',
    'Time to send WhatsApp message'
)
```

### 4. Logging

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "whatsapp_message_received",
    from_number=msg.from_user.wa_id,
    message_id=msg.id,
    workflow_id=workflow_id,
)
```

---

## Cost Estimates

WhatsApp Cloud API pricing (as of 2024):
- **Free Tier**: 1000 conversations/month
- **User-initiated**: $0.005-0.08 per conversation (varies by country)
- **Business-initiated**: $0.016-0.25 per conversation

**Conversation**: 24-hour window after first message

Estimate for 10,000 users:
- Assume 30% active monthly = 3000 conversations
- Cost: ~$150-$750/month (depending on country)

---

## Comparison: PyWa vs Baileys

| Feature | PyWa (Cloud API) | Baileys (Web) |
|---------|------------------|---------------|
| **Language** | Python | Node.js |
| **Official** | ✅ Yes (Meta) | ❌ No (reverse-engineered) |
| **Stability** | ✅ Very stable | ⚠️ Can break with WhatsApp updates |
| **Cost** | 💰 Paid (free tier) | ✅ Free |
| **Setup** | Easy (API tokens) | Medium (QR code, session) |
| **Rate Limits** | High (scalable) | Low (account-based) |
| **Ban Risk** | ✅ None | ⚠️ Possible |
| **Features** | Rich (buttons, templates) | Basic |
| **Business** | ✅ Yes | ❌ Personal use |

**Recommendation**: Use **PyWa (Cloud API)** for production. Use Baileys only for personal projects.

---

## Conclusion

PyWa provides a clean, Python-native way to integrate WhatsApp into the Temporal-based agent system:

✅ **Official API** - No ban risk, stable
✅ **All Python** - Consistent tech stack
✅ **Easy Integration** - Works with FastAPI/Temporal
✅ **Rich Features** - Buttons, media, templates
✅ **Scalable** - Cloud-based, high rate limits
✅ **Production Ready** - Used by businesses worldwide

Next steps:
1. Set up Meta Business Account
2. Get WhatsApp Cloud API credentials
3. Implement webhook handler
4. Test with test phone number
5. Deploy to production with real number

