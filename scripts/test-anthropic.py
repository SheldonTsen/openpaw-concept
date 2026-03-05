"""Quick test: can we call the Anthropic API with the configured key?"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from opentlawpy.config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, LLM_MODEL
from opentlawpy.llm.anthropic_client import AnthropicClient


async def main() -> None:
    print(
        f"API key: {ANTHROPIC_API_KEY[:12]}...{ANTHROPIC_API_KEY[-4:]}"
        if ANTHROPIC_API_KEY
        else "API key: EMPTY"
    )
    print(f"Base URL: {ANTHROPIC_BASE_URL or '(default)'}")
    print(f"Model: {LLM_MODEL}")

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY is not set")
        sys.exit(1)

    client = AnthropicClient(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    result = await client.chat(
        messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
        model=LLM_MODEL,
        max_tokens=32,
    )
    print(f"Response: {result.response_text}")
    print(f"Tokens: {result.input_tokens} in / {result.output_tokens} out")


if __name__ == "__main__":
    asyncio.run(main())
