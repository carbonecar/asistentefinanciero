from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from financial_assistant.telegram.keyboards.inline_keyboards import main_menu_keyboard

command_router = Router(name="commands")


@command_router.message(Command("start"))  # type: ignore[untyped-decorator]
async def on_start(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else "inversor"
    await message.answer(
        f"Hola, {name}! Soy tu asistente financiero personal.\n\n"
        "Puedo ayudarte a:\n"
        "• Analizar el rendimiento de tu cartera\n"
        "• Optimizar tu portfolio\n"
        "• Revisar sentimiento de noticias\n"
        "• Gestionar tus posiciones\n\n"
        "¿Qué querés hacer hoy?",
        reply_markup=main_menu_keyboard(),
    )


@command_router.message(Command("help"))  # type: ignore[untyped-decorator]
async def on_help(message: Message) -> None:
    await message.answer(
        "Comandos disponibles:\n\n"
        "/start — Menú principal\n"
        "/help — Esta ayuda\n\n"
        "También podés escribirme directamente, por ejemplo:\n"
        '"Cómo le fue a mi cartera este año?"\n'
        '"Optimizá mi portfolio con sentimiento"\n'
        '"Qué dicen las noticias sobre AAPL y MSFT?"'
    )


@command_router.message(Command("portfolio"))  # type: ignore[untyped-decorator]
async def on_portfolio(message: Message, graph: object) -> None:
    await message.answer(
        'Para agregar una posición, escribime algo como:\n"Agregar 10 acciones de AAPL a $175 promedio"'
    )
