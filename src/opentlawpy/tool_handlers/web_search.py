import logging

logger = logging.getLogger(__name__)


async def handle(args: dict) -> str:
    logger.info("Calling web_search.")
    return "Error: web_search is not implemented yet"
