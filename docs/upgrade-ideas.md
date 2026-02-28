# Upgrade Ideas for opentlawpy

This document contains enhancements and sophisticated features to consider **after** the initial implementation from `plan.md` is working.

---

## Table of Contents

1. [Gateway Service (Multi-Channel Support)](#gateway-service-multi-channel-support)
2. [Advanced State Compaction](#advanced-state-compaction)
3. [Multi-Model LLM Strategy](#multi-model-llm-strategy)
4. [Semantic Memory Search](#semantic-memory-search)
5. [Cost Tracking & Optimization](#cost-tracking--optimization)
6. [Advanced Tool System](#advanced-tool-system)
7. [Multi-Agent Collaboration](#multi-agent-collaboration)
8. [Security & Sandboxing](#security--sandboxing)
9. [Observability & Analytics](#observability--analytics)
10. [Advanced Error Handling](#advanced-error-handling)
11. [Advanced Parallelization & Scaling](#advanced-parallelization--scaling)

---

## 1. Gateway Service (Multi-Channel Support)

### Current (MVP in plan.md)
- **WhatsApp Poller only**: Single channel (WhatsApp via Green API)
- Polling-based: Checks for messages every 5 seconds
- Directly signals Temporal workflows
- Simple, works for personal use

### Upgrade: HTTP Gateway for Multi-Channel Support

**Why Add Gateway:**
- Support multiple channels: HTTP API, Slack, Email, Telegram, etc.
- Allow direct HTTP access to agent (not just WhatsApp)
- Centralized authentication and routing
- Webhooks from external services

**Architecture:**

```
External Channels          Gateway Service         Temporal
─────────────────          ───────────────         ────────

POST /api/messages     →   FastAPI Server      →   Signal workflow
Slack webhook          →   Authentication      →   Start/signal
Email webhook          →   Routing logic       →   Execute
Telegram bot           →   Convert to signal   →   Continue
Manual API calls       →   Validate request    →   Process

WhatsApp Poller        →   (bypasses gateway)  →   Direct signal
```

### Implementation

**1. FastAPI Gateway Service**

```python
# gateway/main.py

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from temporalio.client import Client
from typing import Optional
import os
import hmac
import hashlib

app = FastAPI(title="opentlawpy Gateway")

# Initialize Temporal client
temporal_client: Optional[Client] = None

@app.on_event("startup")
async def startup():
    """Connect to Temporal on startup."""
    global temporal_client
    temporal_client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    )

# ============= Data Models =============

class MessageRequest(BaseModel):
    """Generic message request for any channel."""
    user_id: str
    message: str
    channel: str = "http"  # http, slack, email, telegram
    session_id: Optional[str] = None
    metadata: dict = {}

class MessageResponse(BaseModel):
    """Response after routing message."""
    status: str  # "delivered", "started", "queued"
    workflow_id: str
    message: str

class SlackEvent(BaseModel):
    """Slack event structure."""
    type: str
    event: dict
    challenge: Optional[str] = None

# ============= Authentication =============

async def verify_api_key(x_api_key: str = Header(...)):
    """Verify API key for HTTP requests."""
    expected_key = os.getenv("GATEWAY_API_KEY")
    if not expected_key:
        return  # No auth configured

    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

async def verify_slack_signature(
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...),
    body: bytes = Depends(lambda: b"")
):
    """Verify Slack webhook signature."""
    slack_signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    if not slack_signing_secret:
        return

    # Verify signature (Slack security)
    sig_basestring = f"v0:{x_slack_request_timestamp}:{body.decode()}"
    expected_signature = 'v0=' + hmac.new(
        slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, x_slack_signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

# ============= Helper Functions =============

async def route_to_workflow(
    workflow_id: str,
    sender: str,
    message: str
) -> MessageResponse:
    """
    Route message to appropriate workflow.

    Strategy:
    1. Try to signal existing workflow
    2. If not found, start new workflow
    3. Then signal the new workflow
    """
    from workflows import AgentWorkflow, WorkflowConfig

    try:
        # Try to get existing workflow
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Workflow exists → send signal
        await handle.signal("new_message", sender, message)

        return MessageResponse(
            status="delivered",
            workflow_id=workflow_id,
            message="Message delivered to existing conversation"
        )

    except Exception:
        # No workflow found → start new one
        config = WorkflowConfig(
            llm_model=os.getenv("LLM_MODEL", "claude-sonnet-4.5"),
            max_duration_minutes=60,
            heartbeat_interval_minutes=30,
            tools=[...]  # Load from config
        )

        handle = await temporal_client.start_workflow(
            AgentWorkflow.run,
            config,
            id=workflow_id,
            task_queue="agent-tasks"
        )

        # Send initial message
        await handle.signal("new_message", sender, message)

        return MessageResponse(
            status="started",
            workflow_id=workflow_id,
            message="New conversation started"
        )

# ============= HTTP Endpoints =============

@app.post("/api/messages", response_model=MessageResponse)
async def handle_http_message(
    request: MessageRequest,
    _auth: None = Depends(verify_api_key)
):
    """
    Main HTTP endpoint for sending messages.

    Usage:
    curl -X POST http://localhost:8000/api/messages \
      -H "Content-Type: application/json" \
      -H "X-API-Key: your-secret-key" \
      -d '{
        "user_id": "alice",
        "message": "Find all TODO comments",
        "channel": "http",
        "session_id": "session-42"
      }'
    """

    # Build workflow ID
    if request.session_id:
        workflow_id = f"{request.channel}-{request.user_id}-{request.session_id}"
    else:
        workflow_id = f"{request.channel}-{request.user_id}"

    return await route_to_workflow(
        workflow_id=workflow_id,
        sender=request.user_id,
        message=request.message
    )

@app.get("/api/conversations/{workflow_id}")
async def get_conversation(
    workflow_id: str,
    _auth: None = Depends(verify_api_key)
):
    """
    Get current state of a conversation.

    Usage:
    curl http://localhost:8000/api/conversations/http-alice-session-42 \
      -H "X-API-Key: your-secret-key"
    """
    try:
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Query workflow for current state
        state = await handle.query("get_state")

        return {
            "workflow_id": workflow_id,
            "status": "running",
            "state": state
        }
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow not found: {workflow_id}"
        )

@app.post("/api/conversations/{workflow_id}/stop")
async def stop_conversation(
    workflow_id: str,
    _auth: None = Depends(verify_api_key)
):
    """
    Gracefully stop a conversation.

    Usage:
    curl -X POST http://localhost:8000/api/conversations/http-alice-session-42/stop \
      -H "X-API-Key: your-secret-key"
    """
    try:
        handle = temporal_client.get_workflow_handle(workflow_id)
        await handle.signal("stop")

        return {
            "status": "stopping",
            "workflow_id": workflow_id,
            "message": "Stop signal sent"
        }
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow not found: {workflow_id}"
        )

# ============= Slack Integration =============

@app.post("/webhooks/slack")
async def slack_webhook(
    event: SlackEvent,
    _auth: None = Depends(verify_slack_signature)
):
    """
    Handle Slack event webhooks.

    Setup:
    1. Create Slack app at api.slack.com/apps
    2. Enable Event Subscriptions
    3. Subscribe to bot events: message.channels, app_mention
    4. Set Request URL to: https://your-domain.com/webhooks/slack
    5. Install app to workspace
    """

    # Slack challenge verification (first time setup)
    if event.type == "url_verification":
        return {"challenge": event.challenge}

    # Handle message event
    if event.type == "event_callback":
        slack_event = event.event

        # Ignore bot messages to prevent loops
        if slack_event.get("bot_id"):
            return {"ok": True}

        # Extract message details
        channel = slack_event.get("channel")
        user = slack_event.get("user")
        text = slack_event.get("text", "")
        thread_ts = slack_event.get("thread_ts") or slack_event.get("ts")

        # Build workflow ID from Slack thread
        workflow_id = f"slack-{channel}-{thread_ts}"

        # Route to workflow
        await route_to_workflow(
            workflow_id=workflow_id,
            sender=user,
            message=text
        )

        return {"ok": True}

    return {"ok": True}

# ============= Email Integration =============

@app.post("/webhooks/email")
async def email_webhook(request: dict):
    """
    Handle incoming emails (via SendGrid, Mailgun, etc.)

    Setup (SendGrid example):
    1. Go to SendGrid → Settings → Inbound Parse
    2. Add domain and URL: https://your-domain.com/webhooks/email
    3. Configure MX records for email domain
    4. Emails to agent@yourdomain.com → forwarded here
    """

    # Parse email (format varies by provider)
    from_email = request.get("from", "")
    subject = request.get("subject", "")
    body = request.get("text", "")

    # Clean email for workflow ID
    email_clean = from_email.replace("@", "-at-").replace(".", "-")
    workflow_id = f"email-{email_clean}"

    # Combine subject and body
    message = f"Subject: {subject}\n\n{body}" if subject else body

    # Route to workflow
    await route_to_workflow(
        workflow_id=workflow_id,
        sender=from_email,
        message=message
    )

    return {"status": "processed"}

# ============= Telegram Integration =============

@app.post("/webhooks/telegram")
async def telegram_webhook(update: dict):
    """
    Handle Telegram bot updates.

    Setup:
    1. Create bot via @BotFather on Telegram
    2. Get bot token
    3. Set webhook:
       curl https://api.telegram.org/bot<TOKEN>/setWebhook \
         -d url=https://your-domain.com/webhooks/telegram
    """

    # Parse Telegram update
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return {"ok": True}

    # Build workflow ID
    workflow_id = f"telegram-{chat_id}"

    # Route to workflow
    await route_to_workflow(
        workflow_id=workflow_id,
        sender=str(user_id),
        message=text
    )

    return {"ok": True}

# ============= Health & Status =============

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "temporal_connected": temporal_client is not None,
        "service": "gateway"
    }

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "opentlawpy Gateway",
        "version": "1.0.0",
        "endpoints": {
            "messages": "POST /api/messages",
            "conversations": "GET /api/conversations/{workflow_id}",
            "slack": "POST /webhooks/slack",
            "email": "POST /webhooks/email",
            "telegram": "POST /webhooks/telegram",
            "health": "GET /health"
        }
    }
```

### 2. Docker Compose Configuration

```yaml
# docker-compose.yml (add gateway service)

services:
  gateway:
    build: ./gateway
    ports:
      - "8000:8000"
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - GATEWAY_API_KEY=${GATEWAY_API_KEY}
      - SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET}
      - LLM_MODEL=claude-sonnet-4.5
    depends_on:
      - temporal
    restart: unless-stopped
```

### 3. Configuration

```bash
# .env

# Gateway
GATEWAY_API_KEY=your-secret-key-here
GATEWAY_PORT=8000

# Slack (optional)
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

# Telegram (optional)
TELEGRAM_BOT_TOKEN=...

# Email (optional)
SENDGRID_API_KEY=...
```

### When to Add Gateway

**Add Gateway when you want:**
- ✅ HTTP API access to agent (curl commands, web app)
- ✅ Slack integration (team chat with agent)
- ✅ Email integration (send emails to agent)
- ✅ Telegram bot
- ✅ Multiple channels simultaneously
- ✅ Authentication and rate limiting
- ✅ Centralized routing logic

**Keep it simple (no gateway) when:**
- ✅ Only WhatsApp integration needed
- ✅ Personal use only
- ✅ Want minimal complexity
- ✅ Poller is sufficient

### Benefits

**With Gateway:**
```
User: curl -X POST http://agent.yourdomain.com/api/messages \
  -H "X-API-Key: secret" \
  -d '{"user_id": "alice", "message": "Find TODOs"}'

→ Gateway routes to Temporal
→ Agent processes
→ Response available via HTTP
```

**Multi-channel example:**
```
Alice (Slack): "@agent find TODOs"
Bob (Telegram): "find TODOs"
Carol (HTTP): POST /api/messages
Dave (WhatsApp): "find TODOs"

All route through same Temporal workflows
Each has separate conversation (workflow_id)
```

---

## 2. Advanced State Compaction

### Current (MVP in plan.md)
- Simple threshold: Compact when > 100 messages
- Keep first 5 + last 20, summarize middle
- Works, but basic

### Upgrade: Hybrid Multi-Factor Compaction

**Smart Triggers:**
```python
async def _should_compact_state(self) -> bool:
    """Advanced compaction decision with multiple factors."""

    # Factor 1: Message count
    message_count = len(self.state.conversation.messages)
    if message_count < 50:
        return False  # Too short

    # Factor 2: Token estimation
    token_count = self._estimate_conversation_tokens()
    approaching_limit = token_count > 50000  # 50K of 200K limit

    # Factor 3: Age-based (conversations older than 7 days)
    oldest_message = self.state.conversation.messages[0]
    conversation_age = workflow.now() - oldest_message.timestamp
    is_old = conversation_age > timedelta(days=7)

    # Factor 4: Cost consideration (if spending > $1/call on context)
    estimated_cost = token_count * 0.00001  # $0.01 per 1K tokens
    is_expensive = estimated_cost > 1.0

    # Factor 5: Time since last compaction (don't compact too frequently)
    if self.state.last_compaction_time:
        since_last = workflow.now() - self.state.last_compaction_time
        if since_last < timedelta(minutes=30):
            return False  # Too soon

    # Compact if ANY of these conditions are true
    return (
        message_count > 100 or
        approaching_limit or
        (is_old and message_count > 50) or
        is_expensive
    )
```

**Semantic Importance Scoring:**
```python
async def _compact_with_importance_scoring(self):
    """
    Keep important messages even if they're old.

    Instead of blindly keeping first 5 + last 20,
    analyze which messages are most important.
    """

    # Call LLM to score message importance
    importance_scores = await workflow.execute_activity(
        score_message_importance_activity,
        MessageImportanceInput(
            messages=self.state.conversation.messages,
            criteria=[
                "Contains user preferences or instructions",
                "Key decisions or outcomes",
                "Unresolved tasks or questions",
                "Error messages or warnings",
                "Configuration changes"
            ]
        )
    )

    # Keep high-importance messages + recent messages
    keep_messages = []
    for msg, score in zip(self.state.conversation.messages, importance_scores):
        if score > 0.7 or msg in recent_messages:
            keep_messages.append(msg)

    # Summarize low-importance messages
    summarize_messages = [
        msg for msg, score in zip(messages, importance_scores)
        if score <= 0.7 and msg not in recent_messages
    ]
```

**Multi-Level Summarization:**
```python
# Instead of one summary, create hierarchical summaries:

# Level 1: Daily summaries
## 2025-01-10 Summary (45 messages)
User worked on database optimization...

## 2025-01-11 Summary (38 messages)
User debugged authentication issues...

# Level 2: Weekly summary
Week of Jan 10-17 (250 messages → 2 daily summaries)
- Optimized database queries (40% faster)
- Fixed auth bug with JWT tokens
- Deployed to staging

# This preserves more context while still compacting
```

**Configuration:**
```python
@dataclass
class AdvancedCompactionConfig:
    enabled: bool = True

    # Multi-factor triggers
    message_threshold: int = 100
    token_threshold: int = 50000
    age_threshold_days: int = 7
    cost_threshold_dollars: float = 1.0
    min_compaction_interval_minutes: int = 30

    # Preservation strategy
    keep_recent_count: int = 20
    keep_first_count: int = 5
    importance_threshold: float = 0.7  # 0-1 score

    # Summarization
    summary_model: str = "claude-haiku-4.5"  # Cheap for summaries
    hierarchical_summaries: bool = True
    summary_interval_days: int = 1  # Daily summaries
```

---

## 2. Multi-Model LLM Strategy

### Current (MVP in plan.md)
- Single model for all tasks (e.g., Claude Opus)
- Works, but expensive

### Upgrade: Smart Model Selection

**Route by Task Complexity:**
```python
async def _call_llm_with_smart_routing(self, task_type: str):
    """Select best model for the task."""

    # Analyze task complexity
    complexity = self._analyze_task_complexity()

    # Route to appropriate model
    if task_type == "routing" or complexity == "simple":
        model = "claude-haiku-4.5"      # $0.25/$1.25 per MTok
        # Fast, cheap: routing decisions, simple queries

    elif complexity == "moderate":
        model = "claude-sonnet-4.5"     # $3/$15 per MTok
        # Balanced: most agent tasks

    elif complexity == "complex" or task_type == "planning":
        model = "claude-opus-4.6"       # $15/$75 per MTok
        # Powerful: complex reasoning, planning

    return await workflow.execute_activity(
        call_llm_activity,
        LLMCallInput(model=model, messages=self.state.conversation.messages)
    )

def _analyze_task_complexity(self) -> str:
    """Heuristics for task complexity."""
    last_message = self.state.conversation.messages[-1].content

    # Simple: routing, status checks
    simple_patterns = ["status", "check", "list", "show"]
    if any(p in last_message.lower() for p in simple_patterns):
        return "simple"

    # Complex: planning, debugging, multi-step
    complex_patterns = ["debug", "optimize", "plan", "design", "analyze"]
    if any(p in last_message.lower() for p in complex_patterns):
        return "complex"

    # Default: moderate
    return "moderate"
```

**Multi-Provider Fallback:**
```python
# Primary: Claude (best for coding)
# Fallback 1: GPT-4 (if Claude fails)
# Fallback 2: Gemini (if both fail)

@activity.defn
async def call_llm_with_fallback_activity(input: LLMCallInput) -> LLMCallOutput:
    """Try multiple providers with automatic fallback."""

    providers = [
        ("anthropic", "claude-opus-4.6"),
        ("openai", "gpt-4-turbo"),
        ("google", "gemini-1.5-pro")
    ]

    last_error = None
    for provider, model in providers:
        try:
            if provider == "anthropic":
                return await _call_claude(model, input.messages)
            elif provider == "openai":
                return await _call_openai(model, input.messages)
            elif provider == "google":
                return await _call_gemini(model, input.messages)
        except Exception as e:
            activity.logger.warning(f"{provider} failed: {e}")
            last_error = e
            continue  # Try next provider

    raise Exception(f"All LLM providers failed. Last error: {last_error}")
```

---

## 3. Semantic Memory Search

### Current (MVP in plan.md)
- state.md included directly in LLM context
- Simple but limited by token count
- No search capability

### Upgrade: Vector-Based Memory Search

**Why:**
After months of conversation, even with compaction, you might have:
- 50 summary blocks
- 20 recent messages
- Still too much to send every time

**Solution: Semantic Search**

```python
# Store summaries and important messages in vector DB
# When LLM needs context, search for relevant memories

async def _call_llm_with_semantic_context(self, user_message: str):
    """Call LLM with semantically relevant context, not entire history."""

    # 1. Search for relevant memories
    relevant_memories = await workflow.execute_activity(
        search_memory_activity,
        MemorySearchInput(
            query=user_message,
            top_k=10,  # Top 10 relevant memories
            workflow_id=self.state.workflow_id
        )
    )

    # 2. Build context with: current summary + relevant memories + recent messages
    context_messages = (
        [self.state.current_summary] +           # High-level context
        relevant_memories +                       # Semantically relevant
        self.state.conversation.messages[-20:]   # Recent conversation
    )

    # 3. Call LLM with optimized context
    return await workflow.execute_activity(
        call_llm_activity,
        LLMCallInput(messages=context_messages, tools=self.config.tools)
    )
```

**Implementation:**
```python
@activity.defn
async def search_memory_activity(input: MemorySearchInput) -> List[Message]:
    """Search conversation history using vector similarity."""

    # Use vector DB (e.g., ChromaDB, Qdrant, Pinecone)
    from chromadb import Client

    client = Client()
    collection = client.get_or_create_collection(f"memories-{input.workflow_id}")

    # Search for similar messages
    results = collection.query(
        query_texts=[input.query],
        n_results=input.top_k
    )

    # Return relevant messages
    return [
        Message.from_dict(metadata)
        for metadata in results['metadatas'][0]
    ]

@activity.defn
async def index_memory_activity(input: IndexMemoryInput):
    """Add new messages to vector DB for future search."""

    client = Client()
    collection = client.get_or_create_collection(f"memories-{input.workflow_id}")

    # Add messages with embeddings
    for msg in input.messages:
        collection.add(
            documents=[msg.content],
            metadatas=[msg.to_dict()],
            ids=[msg.id]
        )
```

**When to Use:**
- Long-running conversations (> 1000 messages over time)
- Need to reference old context ("What did I say about X last month?")
- Multiple topics in same conversation

**Trade-off:**
- Adds complexity (vector DB deployment)
- But: Enables unlimited conversation length
- MVP doesn't need this - state.md is fine for most cases

---

## 4. Cost Tracking & Optimization

### Current (MVP in plan.md)
- Tracks total LLM calls
- Basic stats

### Upgrade: Detailed Cost Analytics

**Per-Message Cost Tracking:**
```python
@dataclass
class LLMCallMetrics:
    timestamp: datetime
    model: str
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    latency_ms: int
    purpose: str  # "routing", "reasoning", "tool_execution"

# Track all LLM calls
self.state.llm_metrics: List[LLMCallMetrics] = []

# After each call
self.state.llm_metrics.append(LLMCallMetrics(...))
self.state.total_cost += metrics.total_cost
```

**Cost Dashboard:**
```python
# Query endpoint to get cost breakdown
@workflow.query
def get_cost_breakdown(self) -> Dict[str, Any]:
    """Get detailed cost analytics."""

    return {
        "total_cost": self.state.total_cost,
        "cost_by_model": {
            model: sum(m.total_cost for m in self.state.llm_metrics if m.model == model)
            for model in set(m.model for m in self.state.llm_metrics)
        },
        "cost_by_purpose": {
            purpose: sum(m.total_cost for m in self.state.llm_metrics if m.purpose == purpose)
            for purpose in ["routing", "reasoning", "tool_execution", "compaction"]
        },
        "most_expensive_calls": sorted(
            self.state.llm_metrics,
            key=lambda m: m.total_cost,
            reverse=True
        )[:10],
        "average_latency_ms": statistics.mean(m.latency_ms for m in self.state.llm_metrics)
    }
```

**Budget Limits:**
```python
@dataclass
class WorkflowConfig:
    # ... existing ...

    # Budget controls
    max_cost_per_message: float = 0.50  # Warn if message costs > $0.50
    max_daily_cost: float = 10.0        # Stop if daily cost exceeds $10
    cost_alert_threshold: float = 5.0   # Alert at $5

async def _check_budget_limits(self, message_cost: float):
    """Enforce budget limits."""

    if message_cost > self.config.max_cost_per_message:
        workflow.logger.warning(
            f"Expensive message: ${message_cost:.2f} (limit: ${self.config.max_cost_per_message})"
        )

    # Calculate daily cost
    today = workflow.now().date()
    daily_cost = sum(
        m.total_cost for m in self.state.llm_metrics
        if m.timestamp.date() == today
    )

    if daily_cost > self.config.max_daily_cost:
        raise Exception(f"Daily budget exceeded: ${daily_cost:.2f} > ${self.config.max_daily_cost}")
```

---

## 5. Advanced Tool System

### Current (MVP in plan.md)
- Markdown-based tool definitions (TOOL.md files)
- Tier-based filtering (essential + common tiers only)
- Static limits: max 30 tools, 15K chars
- Tools sorted by priority, truncated to fit budget

### Upgrade: Dynamic Tool Registry

**Plugin-Style Tools:**
```python
class ToolRegistry:
    """Register tools dynamically."""

    def __init__(self):
        self.tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        """Add new tool."""
        self.tools[tool.name] = tool

    def get_definitions(self) -> List[Dict]:
        """Get tool definitions for LLM."""
        return [tool.to_openai_format() for tool in self.tools.values()]

# Define custom tools
@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict
    activity_name: str  # Which activity to call
    timeout_seconds: int = 300

# Register tools
registry = ToolRegistry()
registry.register(Tool(
    name="bash",
    description="Execute bash command",
    parameters={...},
    activity_name="bash_executor_activity"
))
registry.register(Tool(
    name="search_web",
    description="Search the web",
    parameters={...},
    activity_name="web_search_activity"
))
registry.register(Tool(
    name="query_database",
    description="Query PostgreSQL database",
    parameters={...},
    activity_name="database_query_activity"
))

# Use in workflow
tools = registry.get_definitions()
llm_response = await call_llm_activity(messages, tools)
```

**Conditional Tools:**
```python
# Enable tools based on context or permissions

def get_available_tools(self, user_role: str) -> List[Tool]:
    """Return tools available to this user."""

    all_tools = self.tool_registry.tools

    if user_role == "admin":
        return all_tools  # Admins get everything

    if user_role == "developer":
        # Developers get bash, file I/O, but not database admin
        return [t for t in all_tools if t.name not in ["drop_database", "delete_user"]]

    if user_role == "viewer":
        # Viewers get read-only tools
        return [t for t in all_tools if t.name in ["read_file", "search_web"]]

    return []  # No tools for unknown roles
```

### Upgrade: Semantic Tool Selection

**Problem**: Even with tier-based filtering, you might have 100+ tools across all tiers. Static filtering means:
- Irrelevant tools waste context
- Can't use specialized tools on-demand
- Fixed tool set regardless of task

**Solution**: Dynamically select most relevant tools based on conversation context using embeddings.

#### Architecture

```python
# semantic_tool_selector.py
import numpy as np
from openai import AsyncOpenAI
from typing import List
import asyncio

class SemanticToolSelector:
    """Select most relevant tools using semantic similarity"""

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
        cache_embeddings: bool = True
    ):
        self.client = AsyncOpenAI()
        self.model = embedding_model
        self.tool_embeddings: dict[str, list[float]] = {}
        self.cache_embeddings = cache_embeddings

    async def _embed(self, text: str) -> list[float]:
        """Get embedding for text"""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        a_np = np.array(a)
        b_np = np.array(b)
        return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))

    def _extract_context(self, conversation_history: list[dict]) -> str:
        """Extract relevant context from conversation"""
        # Last 3 messages for context
        recent = conversation_history[-3:]
        return "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in recent
        ])

    async def select_tools(
        self,
        conversation_history: list[dict],
        all_tools: list[ToolDefinition],
        max_tools: int = 20,
        max_chars: int = 12_000
    ) -> list[ToolDefinition]:
        """Select most relevant tools for current conversation context"""

        # Extract conversation context
        context = self._extract_context(conversation_history)
        context_embedding = await self._embed(context)

        # Embed all tools (cache for performance)
        embed_tasks = []
        for tool in all_tools:
            if tool.name in self.tool_embeddings:
                continue  # Already cached
            embed_tasks.append(self._embed_tool(tool))

        if embed_tasks:
            await asyncio.gather(*embed_tasks)

        # Calculate relevance scores
        scored_tools = []
        for tool in all_tools:
            tool_embedding = self.tool_embeddings[tool.name]
            similarity = self._cosine_similarity(context_embedding, tool_embedding)

            # Boost score for essential tools
            if tool.tier == "essential":
                similarity += 0.3  # Always prioritize core tools

            scored_tools.append((similarity, tool))

        # Sort by relevance
        scored_tools.sort(key=lambda x: -x[0])

        # Always include essential tools
        essential = [t for _, t in scored_tools if t.tier == "essential"]

        # Add top-ranked non-essential tools
        non_essential = [(score, t) for score, t in scored_tools if t.tier != "essential"]
        remaining_slots = max_tools - len(essential)

        selected = essential + [t for _, t in non_essential[:remaining_slots]]

        # Truncate by character count if needed
        total_chars = sum(len(t.description) for t in selected)
        if total_chars > max_chars:
            # Remove lowest-priority tools until we fit
            selected.sort(key=lambda t: t.priority)
            while total_chars > max_chars and len(selected) > len(essential):
                # Don't remove essential tools
                if selected[-1].tier != "essential":
                    removed = selected.pop()
                    total_chars -= len(removed.description)
                else:
                    break

        return selected

    async def _embed_tool(self, tool: ToolDefinition):
        """Embed a tool's description and cache it"""
        # Use full tool description (includes examples, notes)
        embedding = await self._embed(tool.description)
        if self.cache_embeddings:
            self.tool_embeddings[tool.name] = embedding
```

#### Workflow Integration

```python
# workflows.py
from semantic_tool_selector import SemanticToolSelector

# Initialize selector at module level
tool_selector = SemanticToolSelector(cache_embeddings=True)

# Load ALL available tools (not just essential+common)
ALL_TOOLS = load_tools_from_directory(
    TOOLS_DIR,
    include_tiers=["essential", "common", "specialized", "experimental"],
    max_tools=200,  # Load everything
    max_chars=1_000_000  # No limit when loading
)

@workflow.defn
class AgentWorkflow:
    async def _call_llm(self) -> LLMResponse:
        """Call LLM with dynamically selected tools"""

        # Select relevant tools based on conversation
        selected_tools = await workflow.execute_activity(
            select_relevant_tools_activity,
            {
                "conversation_history": self.conversation_history,
                "all_tools_json": [t.to_dict() for t in ALL_TOOLS],
                "max_tools": 20,
                "max_chars": 12_000
            },
            start_to_close_timeout=timedelta(seconds=30)
        )

        # Convert to LLM format
        tools_for_llm = [
            tool.to_anthropic_format()
            for tool in selected_tools
        ]

        llm_input = {
            "messages": self.conversation_history,
            "tools": tools_for_llm,
            "model": "claude-sonnet-4.5-20250929"
        }

        return await workflow.execute_activity(
            call_anthropic_api,
            llm_input,
            start_to_close_timeout=timedelta(minutes=5)
        )
```

#### Activity Implementation

```python
# activities.py
from semantic_tool_selector import SemanticToolSelector

selector = SemanticToolSelector()

@activity.defn
async def select_relevant_tools_activity(input_data: dict) -> list[dict]:
    """Activity to select relevant tools (non-deterministic)"""

    conversation_history = input_data["conversation_history"]
    all_tools_json = input_data["all_tools_json"]
    max_tools = input_data.get("max_tools", 20)
    max_chars = input_data.get("max_chars", 12_000)

    # Reconstruct tool objects
    all_tools = [ToolDefinition.from_dict(t) for t in all_tools_json]

    # Select relevant tools
    selected = await selector.select_tools(
        conversation_history,
        all_tools,
        max_tools,
        max_chars
    )

    return [t.to_dict() for t in selected]
```

#### Example: Dynamic Selection in Action

**Scenario 1: Code Review Task**

```
User: "Review this Python codebase and find potential bugs"

Context embedding → High similarity with:
  ✅ grep (search code)
  ✅ read_file (read source files)
  ✅ python (run static analysis)
  ✅ bash (run linters)
  ❌ image_gen (irrelevant)
  ❌ video_edit (irrelevant)

Selected: 18 tools focused on code analysis
```

**Scenario 2: Data Visualization Task**

```
User: "Create a chart showing sales trends"

Context embedding → High similarity with:
  ✅ python (matplotlib/plotly)
  ✅ read_file (load data)
  ✅ image_gen (visualization)
  ✅ calculator (compute trends)
  ❌ git (irrelevant)
  ❌ grep (irrelevant)

Selected: 15 tools focused on data + visualization
```

#### Benefits

✅ **Adaptive**: Tool set changes based on task
✅ **Efficient**: Only send relevant tools to LLM
✅ **Scalable**: Can have 100+ tools without bloating every call
✅ **Cost-effective**: Smaller prompts = lower API costs
✅ **Better results**: LLM sees only relevant tools, reduces confusion

#### Costs

- Embedding API calls: ~$0.0001 per selection (text-embedding-3-small)
- Latency: +100-200ms per LLM call
- Complexity: Requires embedding cache management

#### When to Use

- **Production systems** with 50+ tools
- **Multi-domain agents** (code + data + images + etc.)
- **Cost-sensitive** deployments (high volume)
- When you want **specialized tools on-demand** without static bloat

---

## 6. Multi-Agent Collaboration

### Current (MVP in plan.md)
- Single agent per workflow
- Isolated state

### Upgrade: Agent-to-Agent Communication

**Use Case: Complex Task Delegation**

```python
# Main agent delegates specialized tasks to sub-agents

User: "Analyze this codebase and write a report"

Main Agent:
  ↓
  Starts sub-workflow: "Code Analyzer Agent"
    - Analyzes code quality
    - Returns metrics
  ↓
  Starts sub-workflow: "Documentation Agent"
    - Generates documentation
    - Returns formatted docs
  ↓
  Combines results into report
```

**Implementation:**
```python
async def _delegate_to_agent(self, task: str, agent_type: str):
    """Start child workflow for specialized task."""

    # Start child workflow
    child_workflow_id = f"{self.state.workflow_id}-{agent_type}-{uuid4()}"

    handle = await workflow.start_child_workflow(
        AgentWorkflow.run,
        config=WorkflowConfig(
            agent_type=agent_type,
            parent_workflow_id=self.state.workflow_id
        ),
        id=child_workflow_id
    )

    # Wait for result
    result = await handle.result()

    return result
```

**Agent Types:**
- **Code Analyzer**: Analyzes code quality, finds bugs
- **Researcher**: Searches web, compiles information
- **Writer**: Generates reports, documentation
- **DevOps**: Handles deployments, monitoring

---

## 7. Security & Sandboxing

### Current (MVP in plan.md)
- Bash commands run directly
- Trusts LLM output

### Upgrade: Command Sandboxing

**Dangerous Command Detection:**
```python
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",      # Don't delete root
    r":(){ :|:& };:",     # Fork bomb
    r"dd\s+if=/dev/zero", # Disk fill
    r"chmod\s+777",       # Bad permissions
    r"curl.*\|\s*sh",     # Pipe to shell
]

async def bash_executor_with_safety(command: str):
    """Check for dangerous commands before execution."""

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return BashExecuteOutput(
                stdout="",
                stderr=f"BLOCKED: Command matched dangerous pattern: {pattern}",
                exit_code=1
            )

    # Execute in container or chroot
    return await execute_in_sandbox(command)
```

**Container-Based Execution:**
```python
# Run each bash command in isolated Docker container
docker run --rm \
    --network none \           # No network access
    --cpus=1 \                 # Limit CPU
    --memory=512m \            # Limit RAM
    --read-only \              # Read-only filesystem
    -v /workspace:/workspace \ # Mount workspace
    python:3.11 \
    bash -c "$COMMAND"
```

---

## 8. Observability & Analytics

### Current (MVP in plan.md)
- Temporal UI
- Basic logging

### Upgrade: Comprehensive Monitoring

**Metrics:**
- Messages processed per hour
- Average response time
- Tool usage distribution
- Error rates by tool
- Cost per conversation
- User satisfaction (explicit feedback)

**Dashboards:**
- Grafana dashboards for Temporal metrics
- Custom metrics using Prometheus
- Distributed tracing with OpenTelemetry

**Alerting:**
- Alert if error rate > 5%
- Alert if cost > budget
- Alert if response time > 30s
- Alert if workflow stuck

---

## Summary: Upgrade Path

**Phase 1 (MVP):** Implement `plan.md`
- Basic agent loop
- Simple compaction (> 100 messages)
- Single model (Claude Opus or Sonnet)
- Core tools (bash, file I/O)
- state.md persistence

**Phase 2 (Optimization):** Easy wins
- Multi-model routing (Haiku for simple, Opus for complex)
- Cost tracking
- Better tool error handling

**Phase 3 (Scaling):** When needed
- Advanced compaction (hybrid triggers)
- Semantic memory search (if conversations > 1000 messages)
- Multi-agent collaboration

**Phase 4 (Production):** When serious
- Security sandboxing
- Comprehensive monitoring
- Budget controls
- Advanced analytics

**Don't implement these until MVP works!**

---

## 10. Advanced Error Handling

### Current (MVP in plan.md)
- Basic retry policies (3 attempts, exponential backoff)
- Non-retriable errors for bad credentials
- Return tool errors to LLM
- Simple logging
- Monitor failures in Temporal UI
- Auto-restart on next message

**Works, but basic**

### Upgrade: Production-Grade Error Handling

**When to add:** When you have multiple users and need reliability guarantees

### 1. Circuit Breaker Pattern

**Problem:** API is down, workflow keeps retrying and failing

**Solution:** Stop calling failed service temporarily

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class CircuitBreakerState:
    """Track service health."""
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    is_open: bool = False  # Open = stop calling service

# Workflow-level circuit breaker
class ServiceCircuitBreaker:
    """Stop calling service if it's consistently failing."""

    def __init__(self, failure_threshold: int = 5, timeout_minutes: int = 5):
        self.failure_threshold = failure_threshold
        self.timeout = timedelta(minutes=timeout_minutes)
        self.state = CircuitBreakerState()

    def record_success(self):
        """Service call succeeded - reset circuit breaker."""
        self.state = CircuitBreakerState()  # Reset

    def record_failure(self):
        """Service call failed - increment counter."""
        self.state.failure_count += 1
        self.state.last_failure_time = datetime.now()

        if self.state.failure_count >= self.failure_threshold:
            self.state.is_open = True  # Trip circuit
            workflow.logger.error(
                f"Circuit breaker OPEN - service failing consistently"
            )

    def should_attempt_call(self) -> bool:
        """Should we try calling the service?"""
        if not self.state.is_open:
            return True  # Circuit closed, call OK

        # Circuit open - check if timeout passed
        time_since_failure = datetime.now() - self.state.last_failure_time
        if time_since_failure > self.timeout:
            workflow.logger.info("Circuit breaker attempting recovery")
            return True  # Try again

        return False  # Still in timeout

# Usage in workflow
@workflow.defn
class AgentWorkflow:
    def __init__(self):
        self.llm_circuit_breaker = ServiceCircuitBreaker(
            failure_threshold=5,
            timeout_minutes=5
        )

    async def _call_llm(self):
        """Call LLM with circuit breaker protection."""

        if not self.llm_circuit_breaker.should_attempt_call():
            # Circuit open - don't call
            workflow.logger.warning("LLM circuit breaker OPEN, skipping call")
            return LLMCallOutput(
                response_text="Service temporarily unavailable, please try again later",
                tool_calls=[]
            )

        try:
            result = await workflow.execute_activity(
                call_llm_activity,
                ...
            )
            self.llm_circuit_breaker.record_success()  # Reset on success
            return result

        except Exception as e:
            self.llm_circuit_breaker.record_failure()  # Track failure
            raise
```

**Benefits:**
- Stops hammering failed service
- Gives service time to recover
- Auto-recovers after timeout
- Reduces wasted API calls

---

### 2. Dead Letter Queue

**Problem:** Some messages consistently fail (bad input, bugs)

**Solution:** Move failed messages to separate queue for manual review

```python
@dataclass
class FailedMessage:
    """Message that failed processing."""
    workflow_id: str
    message: str
    error: str
    failure_count: int
    last_attempt: datetime

# Dead letter queue (stored in database/file)
class DeadLetterQueue:
    """Store messages that consistently fail."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.failed_messages: List[FailedMessage] = []

    async def should_move_to_dlq(self, workflow_id: str) -> bool:
        """Check if message has failed too many times."""
        msg = self._find_message(workflow_id)
        return msg and msg.failure_count >= self.max_attempts

    async def add_to_dlq(self, workflow_id: str, message: str, error: str):
        """Move message to dead letter queue."""
        failed_msg = FailedMessage(
            workflow_id=workflow_id,
            message=message,
            error=error,
            failure_count=self.max_attempts,
            last_attempt=datetime.now()
        )
        self.failed_messages.append(failed_msg)

        # Store to file/database
        await self._persist_dlq()

        # Alert admin
        await send_alert(
            f"Message moved to DLQ: {workflow_id}",
            f"Error: {error}"
        )

# Usage in poller
async def _route_message(self, message):
    workflow_id = f"whatsapp-{message.chat_id}"

    # Check dead letter queue
    if await dlq.should_move_to_dlq(workflow_id):
        await dlq.add_to_dlq(workflow_id, message.text, "Max failures reached")
        # Send error to user
        await send_whatsapp_message(
            message.chat_id,
            "I'm having trouble processing your messages. Support has been notified."
        )
        return

    # Try normal processing
    try:
        await self._start_or_signal_workflow(workflow_id, message)
    except Exception as e:
        # Record failure
        await dlq.record_failure(workflow_id, str(e))
```

---

### 3. Automatic Alerting

**Problem:** You don't know when failures occur

**Solution:** Alert on failures via Slack/email/PagerDuty

```python
from enum import Enum

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AlertingSystem:
    """Send alerts for errors."""

    async def alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        workflow_id: Optional[str] = None
    ):
        """Send alert via configured channels."""

        # Slack
        if severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            await self._send_slack_alert(title, message, workflow_id)

        # Email (critical only)
        if severity == AlertSeverity.CRITICAL:
            await self._send_email_alert(title, message)

        # PagerDuty (critical only)
        if severity == AlertSeverity.CRITICAL:
            await self._trigger_pagerduty(title, message)

    async def _send_slack_alert(self, title, message, workflow_id):
        """Send to Slack #alerts channel."""
        await slack_client.chat_postMessage(
            channel="#alerts",
            text=f"🚨 *{title}*\n{message}\nWorkflow: {workflow_id}\n"
                 f"<http://localhost:8080/namespaces/default/workflows/{workflow_id}|View in Temporal UI>"
        )

# Usage in activities
@activity.defn
async def call_llm_activity(input):
    try:
        # ... API call ...
    except anthropic.RateLimitError as e:
        # Warning alert (not critical)
        await alerting.alert(
            AlertSeverity.WARNING,
            "LLM Rate Limit Hit",
            f"Rate limited on model {input.model}. Will retry."
        )
        raise

    except anthropic.AuthenticationError as e:
        # Critical alert (needs immediate fix)
        await alerting.alert(
            AlertSeverity.CRITICAL,
            "LLM Authentication Failed",
            f"Invalid API key! All LLM calls will fail.\nError: {e}"
        )
        raise ApplicationError("Invalid API key", non_retriable=True)
```

---

### 4. Error Rate Monitoring

**Problem:** Don't know overall system health

**Solution:** Track error rates, alert on high failure %

```python
@dataclass
class ErrorMetrics:
    """Track error rates."""
    total_calls: int = 0
    failed_calls: int = 0
    error_rate: float = 0.0
    last_hour_errors: List[datetime] = field(default_factory=list)

class ErrorRateMonitor:
    """Monitor error rates across system."""

    def __init__(self, alert_threshold: float = 0.05):  # 5% error rate
        self.metrics = ErrorMetrics()
        self.alert_threshold = alert_threshold

    def record_call(self, success: bool):
        """Record activity call."""
        self.metrics.total_calls += 1

        if not success:
            self.metrics.failed_calls += 1
            self.metrics.last_hour_errors.append(datetime.now())

        # Calculate error rate
        self.metrics.error_rate = (
            self.metrics.failed_calls / self.metrics.total_calls
        )

        # Clean old errors (only track last hour)
        cutoff = datetime.now() - timedelta(hours=1)
        self.metrics.last_hour_errors = [
            t for t in self.metrics.last_hour_errors if t > cutoff
        ]

        # Alert if error rate too high
        if self.metrics.error_rate > self.alert_threshold:
            self._alert_high_error_rate()

    def _alert_high_error_rate(self):
        """Alert on high error rate."""
        await alerting.alert(
            AlertSeverity.ERROR,
            "High Error Rate Detected",
            f"Error rate: {self.metrics.error_rate:.1%}\n"
            f"Failed calls: {self.metrics.failed_calls}/{self.metrics.total_calls}\n"
            f"Last hour: {len(self.metrics.last_hour_errors)} errors"
        )

# Usage
error_monitor = ErrorRateMonitor(alert_threshold=0.05)

@activity.defn
async def call_llm_activity(input):
    try:
        result = await client.messages.create(...)
        error_monitor.record_call(success=True)
        return result
    except Exception:
        error_monitor.record_call(success=False)
        raise
```

---

### 5. Sophisticated Retry Strategies

**Current:** Simple exponential backoff

**Upgrade:** Jitter, per-error-type strategies, custom backoff

```python
class SmartRetryPolicy:
    """Advanced retry strategies."""

    @staticmethod
    def with_jitter(base_policy: RetryPolicy) -> RetryPolicy:
        """Add jitter to prevent thundering herd."""
        # Jitter: randomize retry interval slightly
        # Instead of all requests retrying at exactly 2s,
        # they retry between 1.5s-2.5s (spread load)
        return RetryPolicy(
            maximum_attempts=base_policy.maximum_attempts,
            initial_interval=base_policy.initial_interval,
            maximum_interval=base_policy.maximum_interval,
            backoff_coefficient=base_policy.backoff_coefficient,
            # Add jitter (not directly supported, needs custom implementation)
        )

    @staticmethod
    def for_rate_limit() -> RetryPolicy:
        """Aggressive retries for rate limits."""
        return RetryPolicy(
            maximum_attempts=5,  # More attempts
            initial_interval=timedelta(seconds=5),   # Start with longer wait
            maximum_interval=timedelta(seconds=60),  # Wait up to 1 min
            backoff_coefficient=2.0
        )

    @staticmethod
    def for_network_issue() -> RetryPolicy:
        """Quick retries for network."""
        return RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=5),
            backoff_coefficient=1.5
        )

    @staticmethod
    def for_database() -> RetryPolicy:
        """Minimal retries for database."""
        return RetryPolicy(
            maximum_attempts=2,
            initial_interval=timedelta(milliseconds=500),
            maximum_interval=timedelta(seconds=2),
            backoff_coefficient=1.0
        )

# Usage
await workflow.execute_activity(
    call_llm_activity,
    input,
    retry_policy=SmartRetryPolicy.for_rate_limit()  # ← Specific policy
)
```

---

### 6. User Error Notifications

**Problem:** Users don't know when errors occur

**Solution:** Report errors back to WhatsApp

```python
async def _handle_workflow_error(self, error: Exception):
    """Report error to user via WhatsApp."""

    # Classify error
    if isinstance(error, anthropic.RateLimitError):
        user_message = (
            "I'm experiencing high demand right now. "
            "Please try again in a few minutes."
        )
    elif isinstance(error, anthropic.AuthenticationError):
        user_message = (
            "I'm having technical difficulties. "
            "Support has been notified."
        )
    else:
        user_message = (
            "I encountered an unexpected error. "
            "I'll try again - please resend your message."
        )

    # Send to user via WhatsApp
    await workflow.execute_activity(
        send_whatsapp_message_activity,
        SendMessageInput(
            chat_id=self.state.workflow_id.replace("whatsapp-", ""),
            message=user_message
        )
    )

    # Add to conversation history
    self.state.conversation.messages.append(
        Message(
            role=MessageRole.SYSTEM,
            content=f"[Error occurred: {type(error).__name__}]"
        )
    )
```

---

### Summary: When to Add Advanced Error Handling

**Add when you have:**
- ✅ Multiple users (not just personal use)
- ✅ Production deployment
- ✅ SLA requirements
- ✅ Need to know about failures immediately
- ✅ High error rates (> 1%)

**Don't add for MVP:**
- Keep it simple
- Basic retry policies are enough
- Temporal UI shows failures
- Auto-restart on next message works fine

**Progression:**
1. **MVP:** Basic retries + logging
2. **Phase 2:** Alerting (Slack)
3. **Phase 3:** Circuit breakers, DLQ
4. **Phase 4:** Full monitoring, sophisticated retries

---

## 11. Advanced Parallelization & Scaling

### Current (MVP in plan.md)
- **Tool execution**: Parallel with `asyncio.gather` (3x+ speedup)
- **Multiple workflows**: Automatic via Temporal (10-20 concurrent chats)
- **Single worker**: One worker, one task queue
- **Good for**: Personal use, 10-20 concurrent users

**Works well for MVP, but limited scalability**

### Upgrade: Production-Scale Parallelization

**When to add:** When you need to handle 100+ concurrent users or have specialized workloads

---

### 1. Task Queue Separation

**Problem:** Different activities have different resource requirements

```
LLM calls:  High latency (1-5s), I/O bound, API rate limits
Bash:       CPU intensive, potentially long-running
File I/O:   Fast (< 100ms), high throughput
GPU tools:  Need GPU workers
```

**Solution:** Separate task queues for different activity types

```python
# Worker 1: LLM Activities
async def start_llm_worker():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="llm-activities",
        activities=[call_anthropic_api, call_openai_api],
        max_concurrent_activities=50,  # High concurrency for I/O-bound
        max_concurrent_activity_task_polls=10
    )

    await worker.run()

# Worker 2: CPU Activities
async def start_cpu_worker():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="cpu-activities",
        activities=[execute_bash_command, run_python_code],
        max_concurrent_activities=4,  # CPU count
        max_concurrent_activity_task_polls=2
    )

    await worker.run()

# Worker 3: I/O Activities
async def start_io_worker():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="io-activities",
        activities=[read_file_activity, write_file_activity, whatsapp_send_message],
        max_concurrent_activities=100,  # Very high for fast I/O
        max_concurrent_activity_task_polls=20
    )

    await worker.run()

# Worker 4: GPU Activities (specialized)
async def start_gpu_worker():
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="gpu-activities",
        activities=[image_generation_activity, video_processing_activity],
        max_concurrent_activities=1,  # One GPU job at a time
        max_concurrent_activity_task_polls=1
    )

    await worker.run()
```

**Route activities to appropriate queues:**

```python
async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
    """Route tool to appropriate task queue"""

    # Determine task queue based on tool
    if tool_call.name in ["call_llm", "web_search"]:
        task_queue = "llm-activities"
    elif tool_call.name in ["bash", "python", "compile"]:
        task_queue = "cpu-activities"
    elif tool_call.name in ["read_file", "write_file", "whatsapp_send"]:
        task_queue = "io-activities"
    elif tool_call.name in ["generate_image", "edit_video"]:
        task_queue = "gpu-activities"
    else:
        task_queue = "agent-tasks"  # Default queue

    result = await workflow.execute_activity(
        get_activity_for_tool(tool_call.name),
        tool_call.arguments,
        task_queue=task_queue,  # Route to specialized queue
        start_to_close_timeout=timedelta(seconds=30)
    )

    return result
```

**Benefits:**
- ✅ LLM activities don't block CPU work
- ✅ CPU work doesn't block fast I/O
- ✅ GPU jobs run on dedicated hardware
- ✅ Can scale each queue independently

---

### 2. Horizontal Worker Scaling

**Problem:** Single worker can't handle load

**Solution:** Run multiple workers, Temporal load-balances automatically

**Docker Compose scaling:**

```yaml
# docker-compose.yml
version: '3.8'

services:
  temporal:
    image: temporalio/auto-setup:latest
    ports:
      - "7233:7233"

  # Scale this service to N instances
  worker:
    build: .
    command: python -m src.worker
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - WORKER_ID=${HOSTNAME}
    deploy:
      replicas: 5  # Run 5 worker instances
    depends_on:
      - temporal
```

**Start multiple workers:**

```bash
# Scale up to 10 workers
docker-compose up --scale worker=10

# Temporal automatically distributes work across all workers!
```

**Performance:**

```
1 Worker:  ~20 concurrent workflows
5 Workers: ~100 concurrent workflows
10 Workers: ~200 concurrent workflows
```

---

### 3. Smart Tool Batching

**Problem:** LLM makes 50 tool calls, each takes 1s (50s sequential, 50s parallel if limited concurrency)

**Solution:** Batch similar tools together intelligently

```python
async def _execute_tools_with_batching(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
    """
    Execute tools with intelligent batching for performance.

    Example: 20 file reads → Single activity that reads all files
    """

    # Group tools by type
    batches = self._group_tools_by_type(tool_calls)

    results = []

    for tool_type, calls in batches.items():
        if tool_type == "read_file" and len(calls) > 5:
            # Batch read: Read all files in one activity
            result = await workflow.execute_activity(
                batch_read_files_activity,
                {"file_paths": [c.arguments["path"] for c in calls]},
                task_queue="io-activities"
            )

            # Unpack results
            for i, file_result in enumerate(result):
                results.append(ToolResult(
                    tool_call_id=calls[i].id,
                    output=file_result["content"],
                    success=file_result["success"]
                ))

        else:
            # Execute normally (parallel)
            batch_results = await asyncio.gather(*[
                self._execute_single_tool(call) for call in calls
            ])
            results.extend(batch_results)

    return results

def _group_tools_by_type(self, tool_calls: List[ToolCall]) -> Dict[str, List[ToolCall]]:
    """Group tool calls by type for batching"""
    groups = {}
    for call in tool_calls:
        if call.name not in groups:
            groups[call.name] = []
        groups[call.name].append(call)
    return groups
```

**Example:**

```python
# LLM requests 20 file reads
tool_calls = [
    {"name": "read_file", "input": {"path": "file1.py"}},
    {"name": "read_file", "input": {"path": "file2.py"}},
    ... # 20 total
]

# Without batching: 20 activities (even if parallel, overhead)
# With batching: 1 activity (reads all 20 files)

# Performance: 20s → 2s (10x faster!)
```

---

### 4. Activity Caching

**Problem:** Same activity called repeatedly (e.g., reading same file)

**Solution:** Cache activity results in workflow memory

```python
@workflow.defn
class AgentWorkflow:
    def __init__(self):
        self.activity_cache: Dict[str, Any] = {}

    async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute tool with caching"""

        # Create cache key
        cache_key = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True)}"

        # Check cache
        if cache_key in self.activity_cache:
            workflow.logger.info(f"Cache hit: {cache_key}")
            return self.activity_cache[cache_key]

        # Execute activity
        result = await self._execute_activity_no_cache(tool_call)

        # Cache if successful and cacheable
        if result.success and self._is_cacheable(tool_call.name):
            self.activity_cache[cache_key] = result

        return result

    def _is_cacheable(self, tool_name: str) -> bool:
        """Determine if tool results can be cached"""
        # Read-only operations are cacheable
        return tool_name in ["read_file", "grep", "web_search", "bash"]
```

**Benefits:**
- ✅ Avoid redundant activity executions
- ✅ Faster response times
- ✅ Lower costs (fewer API calls)

**Example:**

```python
# User asks: "What's in app.py?"
# LLM reads app.py → cached

# User asks: "Explain line 10 of app.py"
# LLM reads app.py → cache hit! (instant)
```

---

### 5. Workflow Sharding

**Problem:** Single workflow becomes bottleneck (too much state, too many messages)

**Solution:** Split work across multiple workflows

```python
# Parent workflow orchestrates child workflows
@workflow.defn
class OrchestratorWorkflow:
    """
    Manages multiple sub-agent workflows.

    Use case: Large task requires parallel sub-tasks
    """

    async def run(self, task: str):
        # Split task into subtasks
        subtasks = await self._plan_subtasks(task)

        # Start child workflows for each subtask
        child_handles = []
        for subtask in subtasks:
            handle = await workflow.start_child_workflow(
                AgentWorkflow,
                args=[subtask],
                id=f"subtask-{subtask.id}"
            )
            child_handles.append(handle)

        # Wait for all children to complete
        results = await asyncio.gather(*[
            handle.result() for handle in child_handles
        ])

        # Aggregate results
        return self._merge_results(results)
```

**Use case:**

```
User: "Analyze all Python files in this repo"

Orchestrator:
  ├─ Child 1: Analyze app/*.py
  ├─ Child 2: Analyze tests/*.py
  ├─ Child 3: Analyze utils/*.py
  └─ Child 4: Analyze models/*.py

All run in parallel! ✅
```

---

### 6. Performance Monitoring

**Problem:** Don't know where bottlenecks are

**Solution:** Instrument and measure

```python
from temporalio import activity
import time

@activity.defn
async def execute_bash_command(input: dict):
    """Execute bash with performance tracking"""

    start_time = time.time()

    # Execute command
    result = await _run_bash(input["command"])

    # Track metrics
    duration = time.time() - start_time
    activity.heartbeat({
        "tool": "bash",
        "duration": duration,
        "success": result["exit_code"] == 0
    })

    # Log slow operations
    if duration > 10.0:
        activity.logger.warning(
            f"Slow bash command: {input['command'][:50]} took {duration:.2f}s"
        )

    return result
```

**Metrics to track:**
- Tool execution time (p50, p95, p99)
- LLM API latency
- Activity queue depth
- Worker utilization
- Cache hit rate

---

### Performance Comparison

| Optimization | Throughput Gain | Complexity | When to Add |
|--------------|----------------|------------|-------------|
| **Parallel tools** (MVP) | 3x | Low | ✅ Always |
| **Task queues** | 2x | Medium | 100+ users |
| **Worker scaling** | Linear | Low | Load increases |
| **Tool batching** | 5-10x | Medium | Many similar tools |
| **Activity caching** | 10x+ | Low | Repeated operations |
| **Workflow sharding** | Variable | High | Very large tasks |

---

### Summary

**MVP (plan.md):**
- Parallel tool execution with `asyncio.gather`
- Single worker, single queue
- Good for 10-20 concurrent users

**Production Scaling (upgrade-ideas.md):**
- Task queue separation (LLM/CPU/I/O/GPU)
- Horizontal worker scaling (Docker Compose)
- Tool batching for efficiency
- Activity caching for speed
- Workflow sharding for large tasks
- Performance monitoring

**Start simple, scale when needed!**

---

## 12. Kubernetes Deployment

### Current (MVP in plan.md)
- Docker Compose with named volumes (single host)
- Automatic state sharing across workers on same host

### Upgrade: Production Kubernetes with Multi-Node Support

**When you need:**
- Multi-node deployment across servers
- High availability and auto-scaling
- Cloud-native infrastructure (AWS, GCP, Azure)

### Storage (PersistentVolume with NFS/EFS)

```yaml
# k8s/storage.yml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: opentlawpy-state-pv
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteMany  # ⚠️ CRITICAL: Multiple pods read/write
  nfs:
    server: nfs-server.example.com
    path: /mnt/opentlawpy/state
  persistentVolumeReclaimPolicy: Retain

---

apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: opentlawpy-state-pvc
spec:
  accessModes:
    - ReadWriteMany  # ⚠️ CRITICAL
  resources:
    requests:
      storage: 10Gi
  volumeName: opentlawpy-state-pv

---

# Same for workspace
apiVersion: v1
kind: PersistentVolume
metadata:
  name: opentlawpy-workspace-pv
spec:
  capacity:
    storage: 50Gi
  accessModes:
    - ReadWriteMany
  nfs:
    server: nfs-server.example.com
    path: /mnt/opentlawpy/workspace
  persistentVolumeReclaimPolicy: Retain

---

apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: opentlawpy-workspace-pvc
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 50Gi
  volumeName: opentlawpy-workspace-pv
```

**AWS EFS Alternative:**
```yaml
# Using EFS CSI driver
apiVersion: v1
kind: PersistentVolume
metadata:
  name: opentlawpy-state-efs
spec:
  capacity:
    storage: 100Gi
  accessModes:
    - ReadWriteMany
  csi:
    driver: efs.csi.aws.com
    volumeHandle: fs-12345678  # Your EFS ID
  persistentVolumeReclaimPolicy: Retain
```

### Deployment

```yaml
# k8s/deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opentlawpy-worker
spec:
  replicas: 3  # Scale horizontally!
  selector:
    matchLabels:
      app: opentlawpy-worker
  template:
    metadata:
      labels:
        app: opentlawpy-worker
    spec:
      containers:
      - name: worker
        image: opentlawpy:latest
        command: ["python", "-m", "src.worker"]
        env:
        - name: TEMPORAL_ADDRESS
          value: "temporal:7233"
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: opentlawpy-secrets
              key: anthropic-api-key
        volumeMounts:
        - name: state
          mountPath: /app/state
        - name: workspace
          mountPath: /app/workspace
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
      volumes:
      - name: state
        persistentVolumeClaim:
          claimName: opentlawpy-state-pvc
      - name: workspace
        persistentVolumeClaim:
          claimName: opentlawpy-workspace-pvc

---

# WhatsApp Poller (single replica)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: whatsapp-poller
spec:
  replicas: 1  # Only one poller needed
  selector:
    matchLabels:
      app: whatsapp-poller
  template:
    metadata:
      labels:
        app: whatsapp-poller
    spec:
      containers:
      - name: poller
        image: opentlawpy:latest
        command: ["python", "-m", "src.whatsapp.poller"]
        env:
        - name: TEMPORAL_ADDRESS
          value: "temporal:7233"
        - name: GREEN_API_INSTANCE_ID
          valueFrom:
            secretKeyRef:
              name: opentlawpy-secrets
              key: green-api-instance-id
        - name: GREEN_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: opentlawpy-secrets
              key: green-api-token
```

### Deployment Steps

```bash
# 1. Build and push image
docker build -t your-registry/opentlawpy:latest .
docker push your-registry/opentlawpy:latest

# 2. Create namespace
kubectl create namespace opentlawpy

# 3. Create secrets
kubectl create secret generic opentlawpy-secrets \
  --namespace opentlawpy \
  --from-literal=anthropic-api-key=$ANTHROPIC_API_KEY \
  --from-literal=green-api-instance-id=$GREEN_API_INSTANCE_ID \
  --from-literal=green-api-token=$GREEN_API_TOKEN

# 4. Deploy storage (NFS/EFS)
kubectl apply -f k8s/storage.yml --namespace opentlawpy

# 5. Deploy application
kubectl apply -f k8s/deployment.yml --namespace opentlawpy

# 6. Check pods
kubectl get pods --namespace opentlawpy

# 7. View logs
kubectl logs -f deployment/opentlawpy-worker --namespace opentlawpy

# 8. Scale workers
kubectl scale deployment opentlawpy-worker --replicas=10 --namespace opentlawpy

# 9. Update deployment (rolling update)
kubectl set image deployment/opentlawpy-worker \
  worker=your-registry/opentlawpypy:v2 \
  --namespace opentlawpy

# 10. Rollback if needed
kubectl rollout undo deployment/opentlawpy-worker --namespace opentlawpy
```

### When to Use Kubernetes

**Stick with Docker Compose if:**
- Single server deployment
- < 5 workers needed
- Simple infrastructure requirements

**Upgrade to Kubernetes when:**
- Need multi-node deployment
- Auto-scaling based on load
- Running on cloud platforms (EKS, GKE, AKS)
- High availability requirements (pod restarts, node failures)
- Need 10+ workers across multiple servers

### Benefits

✅ **Multi-node scaling**: Deploy across many servers
✅ **Auto-healing**: Pods automatically restart on failure
✅ **Rolling updates**: Zero-downtime deployments
✅ **Resource management**: CPU/memory limits per pod
✅ **Load balancing**: Built-in service discovery

### Costs

❌ **Complexity**: Requires K8s knowledge
❌ **Infrastructure**: Need K8s cluster (managed or self-hosted)
❌ **Storage**: Must configure NFS/EFS for ReadWriteMany
❌ **Networking**: More complex than Docker Compose

**MVP uses Docker Compose. Add Kubernetes when you need multi-node scale!**
