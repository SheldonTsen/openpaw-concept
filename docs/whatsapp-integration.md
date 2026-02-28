# WhatsApp Integration for opentlawpy

## Overview

This document describes how to integrate WhatsApp messaging into the Temporal-based agent system. We'll use the same approach as OpenClaw: **@whiskeysockets/baileys** library for WhatsApp Web protocol implementation.

---

## Architecture Options

### Option 1: WhatsApp Service as Separate Process (Recommended)

```
┌─────────────────────────────────────────────────────────────┐
│                    WhatsApp Service                          │
│  - Maintains WebSocket to WhatsApp servers                  │
│  - Handles authentication (QR code, session)                │
│  - Receives incoming messages                               │
│  - Sends outgoing messages                                  │
│  - Exposes REST/gRPC API                                    │
└──────────────┬──────────────────────────────┬────────────────┘
               │                              │
       (Incoming messages)            (Outgoing messages)
               │                              │
               ▼                              ▲
┌──────────────────────────────────────────────────────────────┐
│                    Gateway Service                           │
│  - Receives WhatsApp messages from WhatsApp Service         │
│  - Converts to Temporal signals                             │
│  - Routes to appropriate agent workflow                     │
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
│  - Send responses via WhatsApp delivery activity           │
└──────────────────────────────────────────────────────────────┘
```

**Pros**:
- WhatsApp connection stays alive independently of Temporal workers
- Can restart workers without disconnecting from WhatsApp
- Easier to scale (one WhatsApp service, multiple workers)
- Better error isolation

**Cons**:
- Additional service to manage
- More network calls

---

### Option 2: WhatsApp in Activity Worker (Not Recommended)

Run WhatsApp client inside activity worker as long-running background process.

**Pros**:
- Fewer moving parts
- Direct integration

**Cons**:
- Worker restart = WhatsApp disconnect
- Temporal activities aren't designed for long-running stateful connections
- Scaling issues (each worker = separate WhatsApp session)

**Recommendation**: Use **Option 1** for production. Option 2 can work for simple prototypes.

---

## Implementation Plan (Option 1)

### 1. WhatsApp Service

**Purpose**: Standalone service that maintains WhatsApp connection and exposes API for sending/receiving messages.

**Technology Stack**:
- Node.js (Baileys requires Node.js)
- Express or Fastify for REST API
- @whiskeysockets/baileys for WhatsApp protocol
- File-based auth storage

**File Structure**:
```
whatsapp-service/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts              # Main entry point
│   ├── whatsapp-client.ts    # Baileys wrapper
│   ├── api.ts                # REST API
│   ├── message-handler.ts    # Incoming message routing
│   └── auth-manager.ts       # QR code, session management
├── auth/                     # Session files (gitignored)
│   └── {phone-number}/
│       ├── creds.json
│       └── *.json
└── Dockerfile
```

#### Code: WhatsApp Client (whatsapp-client.ts)

```typescript
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  type WAMessage,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import qrcode from "qrcode-terminal";
import EventEmitter from "events";

export interface WhatsAppClientOptions {
  authDir: string;
  phoneNumber?: string;
  onQR?: (qr: string) => void;
  onMessage?: (message: IncomingWhatsAppMessage) => void;
}

export interface IncomingWhatsAppMessage {
  from: string;           // E.164 format: +1234567890
  to: string;             // Bot's number
  messageId: string;
  text: string;
  timestamp: number;
  isGroup: boolean;
  groupId?: string;
  senderName?: string;
  quotedMessage?: string;
}

export class WhatsAppClient extends EventEmitter {
  private socket: ReturnType<typeof makeWASocket> | null = null;
  private options: WhatsAppClientOptions;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  constructor(options: WhatsAppClientOptions) {
    super();
    this.options = options;
  }

  async connect(): Promise<void> {
    const { state, saveCreds } = await useMultiFileAuthState(this.options.authDir);
    const { version } = await fetchLatestBaileysVersion();

    this.socket = makeWASocket({
      version,
      auth: state,
      printQRInTerminal: false,
      logger: this.createLogger(),
    });

    // Handle QR code
    this.socket.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr && this.options.onQR) {
        console.log("QR Code received:");
        qrcode.generate(qr, { small: true });
        this.options.onQR(qr);
      }

      if (connection === "close") {
        const shouldReconnect =
          (lastDisconnect?.error as Boom)?.output?.statusCode !== DisconnectReason.loggedOut;

        console.log("Connection closed. Reconnect:", shouldReconnect);

        if (shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          setTimeout(() => this.connect(), 5000 * this.reconnectAttempts);
        } else {
          this.emit("disconnected", lastDisconnect?.error);
        }
      } else if (connection === "open") {
        console.log("WhatsApp connected successfully!");
        this.reconnectAttempts = 0;
        this.emit("connected");
      }
    });

    // Handle credentials update
    this.socket.ev.on("creds.update", saveCreds);

    // Handle incoming messages
    this.socket.ev.on("messages.upsert", async ({ messages, type }) => {
      if (type !== "notify") return;

      for (const msg of messages) {
        await this.handleIncomingMessage(msg);
      }
    });
  }

  private async handleIncomingMessage(msg: WAMessage): Promise<void> {
    // Skip if no message content
    if (!msg.message) return;

    // Extract text
    const text = this.extractText(msg);
    if (!text) return;

    // Parse sender
    const from = msg.key.remoteJid || "";
    const isGroup = from.endsWith("@g.us");
    const sender = isGroup ? msg.key.participant || from : from;

    // Normalize to E.164
    const normalizedSender = this.normalizePhoneNumber(sender);
    const normalizedTo = this.normalizePhoneNumber(this.socket?.user?.id || "");

    const incomingMessage: IncomingWhatsAppMessage = {
      from: normalizedSender,
      to: normalizedTo,
      messageId: msg.key.id || "",
      text,
      timestamp: msg.messageTimestamp as number,
      isGroup,
      groupId: isGroup ? from : undefined,
      senderName: msg.pushName,
    };

    // Emit event
    this.emit("message", incomingMessage);

    // Call callback
    if (this.options.onMessage) {
      this.options.onMessage(incomingMessage);
    }
  }

  private extractText(msg: WAMessage): string | null {
    const messageContent = msg.message;
    if (!messageContent) return null;

    // Handle different message types
    if (messageContent.conversation) {
      return messageContent.conversation;
    } else if (messageContent.extendedTextMessage?.text) {
      return messageContent.extendedTextMessage.text;
    } else if (messageContent.imageMessage?.caption) {
      return messageContent.imageMessage.caption;
    } else if (messageContent.videoMessage?.caption) {
      return messageContent.videoMessage.caption;
    }

    return null;
  }

  private normalizePhoneNumber(jid: string): string {
    // Convert WhatsApp JID to E.164 format
    // Example: 1234567890@s.whatsapp.net -> +1234567890
    const match = jid.match(/^(\d+)@/);
    if (match) {
      return `+${match[1]}`;
    }
    return jid;
  }

  async sendMessage(to: string, text: string): Promise<{ messageId: string }> {
    if (!this.socket) {
      throw new Error("WhatsApp socket not connected");
    }

    // Convert E.164 to JID
    const jid = this.toJID(to);

    const result = await this.socket.sendMessage(jid, { text });

    return {
      messageId: result?.key?.id || "",
    };
  }

  private toJID(phoneOrJid: string): string {
    // If already a JID, return as-is
    if (phoneOrJid.includes("@")) {
      return phoneOrJid;
    }

    // Convert E.164 to JID
    // +1234567890 -> 1234567890@s.whatsapp.net
    const digits = phoneOrJid.replace(/\D/g, "");
    return `${digits}@s.whatsapp.net`;
  }

  async disconnect(): Promise<void> {
    if (this.socket) {
      await this.socket.logout();
      this.socket = null;
    }
  }

  isConnected(): boolean {
    return this.socket !== null;
  }

  private createLogger() {
    // Baileys expects Pino-style logger
    return {
      level: "warn",
      debug: () => {},
      info: () => {},
      warn: console.warn,
      error: console.error,
      fatal: console.error,
      trace: () => {},
    };
  }
}
```

#### Code: REST API (api.ts)

```typescript
import express from "express";
import { WhatsAppClient } from "./whatsapp-client.js";

export function createWhatsAppAPI(whatsappClient: WhatsAppClient) {
  const app = express();
  app.use(express.json());

  // Health check
  app.get("/health", (req, res) => {
    res.json({
      status: whatsappClient.isConnected() ? "connected" : "disconnected",
    });
  });

  // Send message
  app.post("/send", async (req, res) => {
    try {
      const { to, text } = req.body;

      if (!to || !text) {
        return res.status(400).json({ error: "Missing 'to' or 'text'" });
      }

      const result = await whatsappClient.sendMessage(to, text);

      res.json({
        success: true,
        messageId: result.messageId,
      });
    } catch (error) {
      console.error("Send error:", error);
      res.status(500).json({
        success: false,
        error: String(error),
      });
    }
  });

  // Get QR code (for initial login)
  let currentQR: string | null = null;

  whatsappClient.on("qr", (qr: string) => {
    currentQR = qr;
  });

  app.get("/qr", (req, res) => {
    if (currentQR) {
      res.json({ qr: currentQR });
    } else {
      res.status(404).json({ error: "No QR code available" });
    }
  });

  // Webhook registration (where to forward incoming messages)
  let webhookUrl: string | null = null;

  app.post("/webhook", (req, res) => {
    const { url } = req.body;
    webhookUrl = url;
    res.json({ success: true, webhookUrl });
  });

  // Forward incoming messages to webhook
  whatsappClient.on("message", async (msg) => {
    if (webhookUrl) {
      try {
        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(msg),
        });
      } catch (error) {
        console.error("Webhook forward error:", error);
      }
    }
  });

  return app;
}
```

#### Code: Main Entry Point (index.ts)

```typescript
import { WhatsAppClient } from "./whatsapp-client.js";
import { createWhatsAppAPI } from "./api.js";

async function main() {
  const authDir = process.env.WHATSAPP_AUTH_DIR || "./auth/default";
  const port = parseInt(process.env.PORT || "3001");

  console.log("Starting WhatsApp service...");
  console.log("Auth directory:", authDir);

  const client = new WhatsAppClient({
    authDir,
    onQR: (qr) => {
      console.log("Scan this QR code with WhatsApp mobile app:");
      console.log("Or visit http://localhost:" + port + "/qr");
    },
    onMessage: (msg) => {
      console.log(`[${msg.from}]: ${msg.text}`);
    },
  });

  // Connect to WhatsApp
  await client.connect();

  // Start API server
  const app = createWhatsAppAPI(client);
  app.listen(port, () => {
    console.log(`WhatsApp API listening on http://localhost:${port}`);
  });

  // Graceful shutdown
  process.on("SIGINT", async () => {
    console.log("Shutting down...");
    await client.disconnect();
    process.exit(0);
  });
}

main().catch(console.error);
```

---

### 2. Gateway Service Integration

Update the Gateway service to receive WhatsApp messages and forward to Temporal workflows.

**Code: Add WhatsApp webhook endpoint (gateway/routes.py)**

```python
from fastapi import FastAPI, Request
from pydantic import BaseModel
from temporalio.client import Client
import os

app = FastAPI()
temporal_client: Client = None

class WhatsAppMessage(BaseModel):
    from_: str = Field(alias="from")
    to: str
    messageId: str
    text: str
    timestamp: int
    isGroup: bool
    groupId: str | None = None
    senderName: str | None = None

@app.on_event("startup")
async def startup():
    global temporal_client
    temporal_client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    )

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(message: WhatsAppMessage):
    """
    Receive incoming WhatsApp messages from WhatsApp Service.
    Route to appropriate agent workflow.
    """
    # Determine workflow ID based on sender
    # Option 1: One workflow per phone number
    workflow_id = f"agent-whatsapp-{message.from_.replace('+', '')}"

    # Option 2: One workflow per channel (all WhatsApp messages)
    # workflow_id = "agent-whatsapp-main"

    try:
        # Get workflow handle
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Check if workflow exists, if not start it
        try:
            await handle.describe()
        except:
            # Workflow doesn't exist, start it
            from src.workflows.agent_workflow import AgentWorkflow
            from src.models.state import WorkflowConfig

            config = WorkflowConfig(
                max_duration_minutes=60,
                heartbeat_interval_minutes=5,
                # ... other config
            )

            handle = await temporal_client.start_workflow(
                AgentWorkflow.run,
                config,
                id=workflow_id,
                task_queue="agent-workflows",
            )

        # Send message as signal
        await handle.signal(
            "new_message",
            message.from_,
            message.text
        )

        return {
            "status": "delivered",
            "workflow_id": workflow_id
        }

    except Exception as e:
        print(f"Error routing WhatsApp message: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
```

**Configure WhatsApp Service to send to Gateway**:

```bash
# In WhatsApp service
curl -X POST http://gateway:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"url": "http://gateway:8000/webhook/whatsapp"}'
```

---

### 3. WhatsApp Delivery Activity

Add activity to send messages back to WhatsApp.

**Code: whatsapp_delivery.py**

```python
from temporalio import activity
from dataclasses import dataclass
import httpx
import os

@dataclass
class WhatsAppDeliveryInput:
    to: str          # E.164 phone number: +1234567890
    text: str
    account_id: str = "default"

@dataclass
class WhatsAppDeliveryOutput:
    success: bool
    message_id: str | None = None
    error: str | None = None

@activity.defn
async def whatsapp_delivery_activity(
    input: WhatsAppDeliveryInput
) -> WhatsAppDeliveryOutput:
    """Send message via WhatsApp service."""

    whatsapp_service_url = os.getenv(
        "WHATSAPP_SERVICE_URL",
        "http://whatsapp-service:3001"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{whatsapp_service_url}/send",
                json={
                    "to": input.to,
                    "text": input.text
                },
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                return WhatsAppDeliveryOutput(
                    success=True,
                    message_id=data.get("messageId")
                )
            else:
                return WhatsAppDeliveryOutput(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}"
                )

    except Exception as e:
        activity.logger.error(f"WhatsApp delivery error: {e}")
        return WhatsAppDeliveryOutput(
            success=False,
            error=str(e)
        )
```

**Usage in Workflow**:

```python
# In agent_workflow.py

async def _send_response(self, text: str, recipient: str):
    """Send response back to user via WhatsApp."""

    result = await workflow.execute_activity(
        whatsapp_delivery_activity,
        WhatsAppDeliveryInput(
            to=recipient,
            text=text
        ),
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1)
        )
    )

    if not result.success:
        workflow.logger.error(f"Failed to send WhatsApp message: {result.error}")
```

---

### 4. Docker Compose Configuration

Add WhatsApp service to docker-compose.yml:

```yaml
version: '3.8'

services:
  # ... (existing Temporal, worker, gateway services)

  # WhatsApp Service
  whatsapp-service:
    build:
      context: ./whatsapp-service
      dockerfile: Dockerfile
    ports:
      - "3001:3001"
    environment:
      - PORT=3001
      - WHATSAPP_AUTH_DIR=/app/auth
    volumes:
      - ./whatsapp-auth:/app/auth  # Persist session
    restart: unless-stopped

  # Gateway Service (updated)
  gateway:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - WHATSAPP_SERVICE_URL=http://whatsapp-service:3001
    depends_on:
      - temporal
      - whatsapp-service
    command: python -m src.gateway.app
```

---

## Setup & Authentication Flow

### Initial Setup (QR Code Login)

1. **Start WhatsApp service**:
   ```bash
   docker-compose up whatsapp-service
   ```

2. **Get QR code**:
   ```bash
   # Terminal will show QR code, or:
   curl http://localhost:3001/qr
   ```

3. **Scan with WhatsApp mobile app**:
   - Open WhatsApp on your phone
   - Go to Settings → Linked Devices
   - Tap "Link a Device"
   - Scan the QR code

4. **Service is now authenticated**:
   - Session saved in `./whatsapp-auth/`
   - Will auto-reconnect on restart

### Session Persistence

Session files are stored in `./whatsapp-auth/{account}/`:
- `creds.json` - Authentication credentials
- `app-state-sync-*.json` - App state
- `session-*.json` - Session data

**Important**: Keep these files secure and backed up!

---

## Message Flow Examples

### Incoming Message Flow

```
WhatsApp User sends: "Hello bot"
          ↓
WhatsApp Servers
          ↓
Baileys (WhatsApp Service)
          ↓
POST /webhook/whatsapp → Gateway
          ↓
Temporal Signal → Agent Workflow
          ↓
LLM processes message
          ↓
Bash tool executes (if needed)
          ↓
WhatsApp Delivery Activity
          ↓
POST /send → WhatsApp Service
          ↓
Baileys sends via WhatsApp Servers
          ↓
WhatsApp User receives: "Hello! I'm your AI assistant..."
```

### Group Message Handling

WhatsApp groups require special handling:

```python
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(message: WhatsAppMessage):
    if message.isGroup:
        # Only respond if bot is mentioned
        if not is_bot_mentioned(message.text):
            return {"status": "ignored", "reason": "not mentioned"}

        # Strip mention from text
        clean_text = strip_mention(message.text)

        # Use group-specific workflow
        workflow_id = f"agent-whatsapp-group-{message.groupId}"
    else:
        # Direct message
        workflow_id = f"agent-whatsapp-{message.from_.replace('+', '')}"

    # ... rest of routing logic
```

---

## Advanced Features

### 1. Multi-Account Support

Run multiple WhatsApp accounts (different phone numbers):

```bash
# Start multiple instances with different auth dirs
docker run -e WHATSAPP_AUTH_DIR=/app/auth/account1 -v ./auth1:/app/auth whatsapp-service
docker run -e WHATSAPP_AUTH_DIR=/app/auth/account2 -v ./auth2:/app/auth whatsapp-service
```

### 2. Media Messages

Extend WhatsApp client to handle images, videos, documents:

```typescript
async sendImage(to: string, imageUrl: string, caption?: string) {
  const jid = this.toJID(to);

  return await this.socket.sendMessage(jid, {
    image: { url: imageUrl },
    caption: caption
  });
}

async sendDocument(to: string, documentUrl: string, fileName: string) {
  const jid = this.toJID(to);

  return await this.socket.sendMessage(jid, {
    document: { url: documentUrl },
    fileName: fileName,
    mimetype: 'application/pdf'
  });
}
```

### 3. Read Receipts & Typing Indicators

```typescript
async sendTyping(to: string, isTyping: boolean) {
  const jid = this.toJID(to);
  await this.socket.sendPresenceUpdate(isTyping ? 'composing' : 'paused', jid);
}

async markAsRead(messageKey: any) {
  await this.socket.readMessages([messageKey]);
}
```

### 4. Status Monitoring

Add endpoints to monitor connection status:

```typescript
app.get("/status", (req, res) => {
  res.json({
    connected: whatsappClient.isConnected(),
    phoneNumber: whatsappClient.getPhoneNumber(),
    lastMessageAt: whatsappClient.getLastMessageTime(),
    reconnectAttempts: whatsappClient.getReconnectAttempts()
  });
});
```

---

## Security Considerations

### 1. Authentication

- **Protect QR endpoint**: Only expose during initial setup
- **Session files**: Encrypt at rest, restrict file permissions (chmod 600)
- **API authentication**: Add API keys to WhatsApp service endpoints

### 2. Rate Limiting

WhatsApp has rate limits. Implement:

```typescript
import rateLimit from "express-rate-limit";

const limiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 20, // 20 messages per minute per user
  keyGenerator: (req) => req.body.to // Rate limit per recipient
});

app.post("/send", limiter, async (req, res) => {
  // ... send logic
});
```

### 3. Message Validation

```python
def validate_whatsapp_message(message: WhatsAppMessage) -> bool:
    # Verify sender is in allowlist
    if not is_allowed_sender(message.from_):
        return False

    # Check for spam patterns
    if is_spam(message.text):
        return False

    # Rate limit per user
    if is_rate_limited(message.from_):
        return False

    return True
```

---

## Troubleshooting

### Connection Issues

**Symptom**: WhatsApp service keeps disconnecting

**Solutions**:
1. Check if mobile phone is connected to internet
2. Verify session files aren't corrupted
3. Try removing auth directory and re-linking
4. Check for WhatsApp bans (using unofficial clients can lead to temporary bans)

### QR Code Not Showing

**Symptom**: GET /qr returns 404

**Solutions**:
1. Ensure WhatsApp service is fully started
2. Check logs for connection errors
3. Try restarting the service

### Messages Not Delivered

**Symptom**: POST /send returns success but user doesn't receive message

**Solutions**:
1. Verify phone number format (E.164: +1234567890)
2. Check if recipient has blocked the number
3. Verify WhatsApp connection is active
4. Check for rate limiting

---

## Testing

### Unit Tests

```python
# test_whatsapp_delivery.py

@pytest.mark.asyncio
async def test_whatsapp_delivery_success():
    # Mock WhatsApp service
    async with respx.mock:
        respx.post("http://whatsapp-service:3001/send").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "messageId": "msg123"}
            )
        )

        # Call activity
        result = await whatsapp_delivery_activity(
            WhatsAppDeliveryInput(
                to="+1234567890",
                text="Test message"
            )
        )

        assert result.success
        assert result.message_id == "msg123"
```

### Integration Tests

```python
@pytest.mark.integration
async def test_whatsapp_end_to_end():
    # Start WhatsApp service (requires real auth)
    # Send test message
    # Verify workflow receives signal
    # Verify response is sent back
    pass
```

---

## Production Deployment

### Scaling

For high-volume deployments:

1. **Multiple WhatsApp numbers**: Run separate services per number
2. **Load balancing**: Use NGINX to distribute incoming webhooks
3. **Queue buffering**: Add Redis queue between WhatsApp service and Gateway

### Monitoring

Add health checks:

```yaml
# docker-compose.yml
whatsapp-service:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3001/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### Backup

Automate session backup:

```bash
#!/bin/bash
# backup-whatsapp-session.sh

BACKUP_DIR="/backups/whatsapp-sessions/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Copy session files
cp -r ./whatsapp-auth/* "$BACKUP_DIR/"

# Encrypt
tar czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
openssl enc -aes-256-cbc -salt -in "$BACKUP_DIR.tar.gz" -out "$BACKUP_DIR.tar.gz.enc"

# Upload to S3 or backup location
aws s3 cp "$BACKUP_DIR.tar.gz.enc" s3://my-backups/whatsapp-sessions/
```

---

## Alternative: WhatsApp Business API

For enterprise deployments, consider **WhatsApp Business API** (official):

**Pros**:
- Official support
- Higher rate limits
- Better reliability
- Webhook-based (no persistent connection needed)

**Cons**:
- Requires Facebook Business account approval
- Costs money
- More setup complexity

**Integration**: Similar architecture, but replace Baileys with official API client.

---

## Conclusion

WhatsApp integration adds a powerful channel for user interaction. The recommended architecture (separate WhatsApp service + Temporal workflows) provides:

✅ Reliable message delivery
✅ Persistent connection management
✅ Scalable architecture
✅ Full observability via Temporal UI
✅ Easy to extend with media, groups, etc.

Next steps:
1. Implement WhatsApp service
2. Add webhook endpoint to Gateway
3. Create WhatsApp delivery activity
4. Test end-to-end flow
5. Deploy and monitor

