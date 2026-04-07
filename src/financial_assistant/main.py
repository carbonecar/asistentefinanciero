import asyncio
import logging

from financial_assistant.config.settings import Settings
from financial_assistant.infrastructure.container import Container
from financial_assistant.telegram.bot import create_bot, create_dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings()
    container = Container(settings)

    bot = create_bot(settings.telegram_bot_token)
    dp = create_dispatcher(container.graph)

    logger.info("Starting financial assistant bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
