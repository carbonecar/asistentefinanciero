from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from financial_assistant.telegram.handlers.command_handler import command_router
from financial_assistant.telegram.handlers.message_handler import message_router
from financial_assistant.telegram.middleware.session_middleware import GraphMiddleware


def create_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


def create_dispatcher(graph: object) -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(GraphMiddleware(graph))
    dp.include_router(command_router)
    dp.include_router(message_router)
    return dp
