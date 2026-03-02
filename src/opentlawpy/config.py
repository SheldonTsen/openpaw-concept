import os

TASK_QUEUE = "agent-tasks"
NAMESPACE = "opentlawpy"
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
MY_WHATSAPP_NUMBER = os.environ.get("MY_WHATSAPP_NUMBER", "")
NEONIZE_DB_PATH = os.environ.get("NEONIZE_DB_PATH", "./neonize.db")
WORKFLOW_TIMEOUT_MINUTES = int(os.environ.get("WORKFLOW_TIMEOUT_MINUTES", "15"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
