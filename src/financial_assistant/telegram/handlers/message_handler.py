import html
import logging
from typing import Any

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, Message
from langchain_core.messages import HumanMessage

from financial_assistant.agents.state import AgentState

logger = logging.getLogger(__name__)

message_router = Router(name="messages")

INTENT_MESSAGES = {
    "audit": "Auditá mi cartera",
    "optimize": "Optimizá mi portfolio",
    "news": "Mostrame las últimas noticias",
    "add_position": "Quiero agregar una posición",
}


async def _safe_answer(target: Message, text: str) -> None:
    """Send LLM response using HTML mode with escaped text.
    html.escape() neutralizes <, >, & so the LLM output can never produce
    broken entities, while still letting us use <b>/<i> manually if needed.
    """
    await target.answer(html.escape(text), parse_mode=ParseMode.HTML)


@message_router.callback_query(F.data.startswith("intent:"))
async def on_intent_callback(callback: CallbackQuery, graph: Any) -> None:  # noqa: ANN401
    await callback.answer()

    user_id = callback.from_user.id if callback.from_user else 0
    intent = callback.data.split(":")[1]  # type: ignore[union-attr]
    user_message = INTENT_MESSAGES.get(intent, intent)

    await callback.bot.send_chat_action(callback.message.chat.id, "typing")  # type: ignore[union-attr]

    initial_state: AgentState = {
        "user_id": user_id,
        "user_message": user_message,
        "messages": [HumanMessage(content=user_message)],
        "intent": intent,
        "active_tickers": [],
        "period": "1y",
        "use_sentiment": False,
        "market_data_result": None,
        "audit_report": None,
        "quant_result": None,
        "news_results": None,
        "exchange_rates": None,
        "final_response": None,
        "error": None,
    }

    config = {"configurable": {"thread_id": str(user_id)}}

    try:
        result = await graph.ainvoke(initial_state, config=config)
        response_text = result.get("final_response") or "No pude procesar tu consulta. Intentá de nuevo."
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Graph invocation failed for user %s: %s", user_id, exc)
        response_text = "Ocurrió un error inesperado. Por favor intentá de nuevo más tarde."

    if len(response_text) > 4096:
        response_text = response_text[:4090] + "..."

    await _safe_answer(callback.message, response_text)  # type: ignore[arg-type]


@message_router.message(F.text)
async def on_message(message: Message, graph: Any) -> None:  # noqa: ANN401
    user_id = message.from_user.id if message.from_user else 0

    await message.bot.send_chat_action(message.chat.id, "typing")  # type: ignore[union-attr]

    initial_state: AgentState = {
        "user_id": user_id,
        "user_message": message.text or "",
        "messages": [HumanMessage(content=message.text or "")],
        "intent": "",
        "active_tickers": [],
        "period": "1y",
        "use_sentiment": False,
        "market_data_result": None,
        "audit_report": None,
        "quant_result": None,
        "news_results": None,
        "exchange_rates": None,
        "final_response": None,
        "error": None,
    }

    config = {"configurable": {"thread_id": str(user_id)}}

    try:
        result = await graph.ainvoke(initial_state, config=config)
        response_text = result.get("final_response") or "No pude procesar tu consulta. Intentá de nuevo."
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Graph invocation failed for user %s: %s", user_id, exc)
        response_text = "Ocurrió un error inesperado. Por favor intentá de nuevo más tarde."

    if len(response_text) > 4096:
        response_text = response_text[:4090] + "..."

    await _safe_answer(message, response_text)
