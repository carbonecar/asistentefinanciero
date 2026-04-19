from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class GraphMiddleware(BaseMiddleware):
    """Injects the compiled LangGraph into every handler's data dict."""

    def __init__(self, graph: Any) -> None:  # noqa: ANN401
        self._graph = graph

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        data["graph"] = self._graph
        return await handler(event, data)
