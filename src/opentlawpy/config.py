import os

TASK_QUEUE = "agent-tasks"
WHATSAPP_TASK_QUEUE = "whatsapp-tasks"
TERMINAL_TASK_QUEUE = "terminal-tasks"
NAMESPACE = "opentlawpy"
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
MY_WHATSAPP_NUMBER = os.environ.get("MY_WHATSAPP_NUMBER", "")
NEONIZE_DB_PATH = os.environ.get("NEONIZE_DB_PATH", "./neonize.db")
WORKFLOW_TIMEOUT_MINUTES = int(os.environ.get("WORKFLOW_TIMEOUT_MINUTES", "15"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openrouter")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "240.0"))
LOCAL_MODEL_URL = os.environ.get("LOCAL_MODEL_URL", "http://localhost:8888/v1")
SYSTEM_PROMPT = """You are a helpful assistant and an orchestrator.

When multiple tool calls are independent of each other, call them all in the same
response rather than sequentially. When something seems like a complex task,
delegate it to keep your context clean. Remember you are an orchestrator of tasks.

If you are missing something you need, you can always install it via bash.

Think in English.


If you see [HEARTBEAT], this is a regular check in with some tasks for you to do."""
TOOLS_DIR = os.path.join(os.path.dirname(__file__), "tools")
DEFAULT_TOOL_PRIORITY = 999
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "./workspace")
STATE_DIR = os.environ.get("STATE_DIR", "./data/state")
MAX_COMMAND_TIMEOUT = 300
MAX_COMMAND_OUTPUT_BYTES = 100_000
MAX_TOOL_ITERATIONS = 20
TEMPORAL_DEFAULT_RETRIES = 3
TEMPORAL_DEFAULT_TIMEOUT = 60
COMPACTION_THRESHOLD = int(os.environ.get("COMPACTION_THRESHOLD", "50"))
COMPACTION_KEEP_RECENT = int(os.environ.get("COMPACTION_KEEP_RECENT", "2"))
HEARTBEAT_INTERVAL_MINUTES = int(os.environ.get("HEARTBEAT_INTERVAL_MINUTES", "15"))
# HEARTBEAT_MESSAGE = "[HEARTBEAT] Check in on current status and any pending tasks."
HEARTBEAT_MESSAGE = "[HEARTBEAT] Say 'Checking In On You!'"
SUB_AGENT_MAX_ITERATIONS = int(os.environ.get("SUB_AGENT_MAX_ITERATIONS", "10"))
SUB_AGENT_TIMEOUT_MINUTES = int(os.environ.get("SUB_AGENT_TIMEOUT_MINUTES", "10"))
SUB_AGENT_SYSTEM_PROMPT = """You are a sub-agent executing a specific task.
Complete the task thoroughly and return a clear, concise summary of your results.
Do not ask questions — work with what you have.
If you cannot complete the task, explain what went wrong and what you tried.


If you are missing something you need, you can always install it via bash.

Think in English.
"""
