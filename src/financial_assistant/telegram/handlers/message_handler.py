import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from langchain_core.messages import HumanMessage

from financial_assistant.agents.state import AgentState
from aiogram.types import CallbackQuery,Message

logger = logging.getLogger(__name__)

message_router = Router(name="messages")

INTENT_MESSAGES = {
    "audit": "Auditá mi cartera",
    "optimize": "Optimizá mi portfolio",
    "news": "Mostrame las últimas noticias",
    "add_position": "Quiero agregar una posición",
}


@message_router.callback_query(F.data.startswith("intent:"))
async def on_intent_callback(callback: CallbackQuery, graph: Any) -> None:  # noqa: ANN401
    await callback.answer()  # cierra el spinner del botón

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
    except Exception as exc:
        logger.error("Graph invocation failed for user %s: %s", user_id, exc)
        response_text = "Ocurrió un error inesperado. Por favor intentá de nuevo más tarde."

    if len(response_text) > 4096:
        response_text = response_text[:4090] + "..."

    await callback.message.answer(response_text)  # type: ignore[union-attr]


@message_router.message(F.text)
async def on_message(message: Message, graph: Any) -> None:  # noqa: ANN401
    user_id = message.from_user.id if message.from_user else 0

    # Show typing indicator
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
    except Exception as exc:
        logger.error("Graph invocation failed for user %s: %s", user_id, exc)
        response_text = "Ocurrió un error inesperado. Por favor intentá de nuevo más tarde."

    # Telegram message limit is 4096 chars
    if len(response_text) > 4096:
        response_text = response_text[:4090] + "..."

    await message.answer(response_text)



@message_router.callback_query(F.data.startswith("intent:"))
async def on_callback_query(callback_query: CallbackQuery) -> None:
    intent = callback_query.data.split("intent:")[1]
    if intent == "audit":
        await callback_query.message.answer("¡Vamos a auditar tu cartera! 📊")
    elif intent == "optimize":
        await callback_query.message.answer("¡Optimicemos tu portfolio! ⚡")
    elif intent == "news":
        await callback_query.message.answer("¡Revisemos las noticias! 📰")
    elif intent == "add_position":
        await callback_query.message.answer(
            "Para agregar una posición, escribime algo como:\n"
            "_\"Agregar 10 acciones de AAPL a $175 promedio\"_"
        )
    await callback_query.answer()  # Acknowledge the callback query