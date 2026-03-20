import json
import logging
import shlex

from openpaw.tool_handlers._run_bash import run_bash

logger = logging.getLogger(__name__)


async def handle(args: dict, **kwargs) -> str:
    query = args["query"]
    num_results = min(args.get("num_results", 5), 10)

    safe_query = json.dumps(query)
    script = (
        "import json; "
        "from ddgs import DDGS; "
        f"results = DDGS().text({safe_query}, max_results={num_results}); "
        "print(json.dumps(results, indent=2))"
    )
    command = f"python3 -c {shlex.quote(script)}"

    logger.info(f"Calling web_search with query: {query}")
    return await run_bash(command=command, timeout=30)
