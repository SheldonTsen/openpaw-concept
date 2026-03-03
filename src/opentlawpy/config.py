import os

TASK_QUEUE = "agent-tasks"
WHATSAPP_TASK_QUEUE = "whatsapp-tasks"
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
OPENROUTER_TIMEOUT = float(os.environ.get("OPENROUTER_TIMEOUT", "120.0"))
SYSTEM_PROMPT = "You are a helpful assistant."
TOOLS_DIR = os.path.join(os.path.dirname(__file__), "tools")
DEFAULT_TOOL_PRIORITY = 999
