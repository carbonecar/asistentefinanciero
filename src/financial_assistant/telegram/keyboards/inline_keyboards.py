from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Auditar cartera", callback_data="intent:audit"),
                InlineKeyboardButton(text="⚡ Optimizar", callback_data="intent:optimize"),
            ],
            [
                InlineKeyboardButton(text="📰 Noticias", callback_data="intent:news"),
                InlineKeyboardButton(text="➕ Agregar posición", callback_data="intent:add_position"),
            ],
        ]
    )
