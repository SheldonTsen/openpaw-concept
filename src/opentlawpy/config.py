import os

TASK_QUEUE = "agent-tasks"
NAMESPACE = "opentlawpy"
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
MY_WHATSAPP_NUMBER = os.environ.get("MY_WHATSAPP_NUMBER", "")
NEONIZE_DB_PATH = os.environ.get("NEONIZE_DB_PATH", "./neonize.db")
