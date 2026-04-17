import asyncio
import logging
import os

from financial_assistant.config.settings import Settings
from financial_assistant.infrastructure.container import Container
from financial_assistant.telegram.bot import create_bot, create_dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _configure_langsmith(settings: Settings) -> None:
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        logger.info("LangSmith tracing enabled (project: %s)", settings.langchain_project)


async def main() -> None:
    settings = Settings()
    _configure_langsmith(settings)
    container = Container(settings)

    bot = create_bot(settings.telegram_bot_token)
    dp = create_dispatcher(container.graph)

    logger.info("Starting financial assistant bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
