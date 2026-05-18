import asyncio
import html
import logging
import re
import traceback
from typing import Any, cast

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from langchain_core.messages import HumanMessage

from financial_assistant.agents.state import AgentState, Intent
from financial_assistant.telegram.keyboards.inline_keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)

message_router = Router(name="messages")

INTENT_MESSAGES = {
    "audit": "Auditá mi cartera",
    "optimize": "Optimizá mi portfolio",
    "news": "Noticias de mi portfolio",
    "data_fetch": "Quiero registrar una posición",
}

_TYPING_INTERVAL = 4.0  # Telegram typing action expires after 5s

# Etiquetas Telegram permitidas en modo HTML. Estrategia: normalizar markdown bold,
# escapar todo el texto, luego restaurar sólo estas etiquetas.
_SAFE_HTML_TAG = re.compile(r"&lt;(/?)(b|i|u|s|code)&gt;")
_MARKDOWN_BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")
# Asterisco simple en límite de no-palabra: *Auditar* → <b>Auditar</b>
# No aplica entre caracteres alfanuméricos (ej: 5*180, a*b) ni dentro de **doble**.
_MARKDOWN_SINGLE_BOLD = re.compile(r"(?<!\w)\*([^*\n]+?)\*(?!\w)")
_GREETING_RE = re.compile(
    r"^\s*(?:hola|hi|inicio|buenas|hey|menú|menu|comenzar|start)\s*[!?.]*\s*$",
    re.IGNORECASE | re.UNICODE,
)


def _sanitize_for_html_mode(text: str) -> str:
    text = _MARKDOWN_BOLD.sub(r"<b>\1</b>", text)
    text = _MARKDOWN_SINGLE_BOLD.sub(r"<b>\1</b>", text)
    escaped = html.escape(text)
    return _SAFE_HTML_TAG.sub(r"<\1\2>", escaped)


async def _safe_answer(
    target: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    await target.answer(
        _sanitize_for_html_mode(text), parse_mode=ParseMode.HTML, reply_markup=reply_markup
    )


async def _keep_typing(bot: Bot, chat_id: int, stop: asyncio.Event) -> None:
    """Resend typing action every 4s until stop is set (Telegram expires it after 5s)."""
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception:  # pylint: disable=broad-exception-caught
            break
        try:
            await asyncio.wait_for(asyncio.shield(stop.wait()), timeout=_TYPING_INTERVAL)
        except TimeoutError:
            pass


@message_router.callback_query(F.data.startswith("intent:"))
async def on_intent_callback(callback: CallbackQuery, graph: Any) -> None:  # noqa: ANN401
    await callback.answer()

    if not callback.data or not callback.bot or not isinstance(callback.message, Message):
        return

    user_id = callback.from_user.id if callback.from_user else 0
    intent = callback.data.split(":")[1]
    user_message = INTENT_MESSAGES.get(intent, intent)
    logger.info("[Callback] user=%s intent=%s message=%r", user_id, intent, user_message)

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(callback.bot, callback.message.chat.id, stop_typing))

    initial_state: AgentState = {
        "user_id": user_id,
        "user_message": user_message,
        "messages": [HumanMessage(content=user_message)],
        "intents": [cast(Intent, intent)],
        "active_tickers": [],
        "period": "1y",
        "use_sentiment": False,
        "positions": [],
        "market_data_result": None,
        "audit_report": None,
        "quant_result": None,
        "news_results": None,
        "exchange_rates": None,
        "financial_profile": None,
        "risk_warnings": [],
        "explanation_card": None,
        "final_response": None,
        "errors": [],
    }

    config = {"configurable": {"thread_id": str(user_id)}}

    try:
        result = await graph.ainvoke(initial_state, config=config)
        response_text = result.get("final_response") or "No pude procesar tu consulta. Intentá de nuevo."
        if result.get("errors"):
            logger.warning("Graph completed with errors for user %s: %s", user_id, result["errors"])
    except Exception:  # pylint: disable=broad-exception-caught
        logger.error("Graph invocation failed for user %s:\n%s", user_id, traceback.format_exc())
        response_text = "Ocurrió un error inesperado. Por favor intentá de nuevo más tarde."
    finally:
        stop_typing.set()
        await typing_task

    if len(response_text) > 4096:
        response_text = response_text[:4090] + "..."

    await _safe_answer(callback.message, response_text)


@message_router.message(F.text)
async def on_message(message: Message, graph: Any) -> None:  # noqa: ANN401
    if not message.bot:
        return

    # Fast path: greetings → welcome + menu without invoking the graph
    if _GREETING_RE.match(message.text or ""):
        name = message.from_user.first_name if message.from_user else "inversor"
        welcome = (
            f"¡Hola, {name}! Soy tu asistente financiero personal.\n\n"
            "Puedo ayudarte a:\n"
            "• Analizar el rendimiento de tu cartera\n"
            "• Optimizar tu portfolio\n"
            "• Revisar sentimiento de noticias\n"
            "• Gestionar tus posiciones\n\n"
            "¿Qué querés hacer hoy?"
        )
        await _safe_answer(message, welcome, reply_markup=main_menu_keyboard())
        return

    user_id = message.from_user.id if message.from_user else 0

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(message.bot, message.chat.id, stop_typing))

    initial_state: AgentState = {
        "user_id": user_id,
        "user_message": message.text or "",
        "messages": [HumanMessage(content=message.text or "")],
        "intents": [],
        "active_tickers": [],
        "period": "1y",
        "use_sentiment": False,
        "positions": [],
        "market_data_result": None,
        "audit_report": None,
        "quant_result": None,
        "news_results": None,
        "exchange_rates": None,
        "financial_profile": None,
        "risk_warnings": [],
        "explanation_card": None,
        "final_response": None,
        "errors": [],
    }

    config = {"configurable": {"thread_id": str(user_id)}}

    try:
        result = await graph.ainvoke(initial_state, config=config)
        response_text = result.get("final_response") or "No pude procesar tu consulta. Intentá de nuevo."
        if result.get("errors"):
            logger.warning("Graph completed with errors for user %s: %s", user_id, result["errors"])
    except Exception:  # pylint: disable=broad-exception-caught
        logger.error("Graph invocation failed for user %s:\n%s", user_id, traceback.format_exc())
        response_text = "Ocurrió un error inesperado. Por favor intentá de nuevo más tarde."
    finally:
        stop_typing.set()
        await typing_task

    if len(response_text) > 4096:
        response_text = response_text[:4090] + "..."

    await _safe_answer(message, response_text)
