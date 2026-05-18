import logging
import re
from decimal import Decimal
from typing import Any

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import AddPositionCommand, FetchMarketDataCommand
from financial_assistant.application.services.market_data_service import MarketDataService
from financial_assistant.application.services.portfolio_service import PortfolioService
from financial_assistant.domain.models.portfolio import AssetType

logger = logging.getLogger(__name__)

# Tickers válidos: letras, dígitos, punto (GGAL.BA), caret (^GSPC), guion (BRK-B). Máx 20 chars.
_TICKER_RE = re.compile(r"^[\w.\^\-]{1,20}$")

_VALID_PERIODS: frozenset[str] = frozenset(
    {
        "1d",
        "5d",
        "1mo",
        "3mo",
        "6mo",
        "1y",
        "2y",
        "5y",
        "10y",
        "ytd",
        "max",
    }
)
_DEFAULT_PERIOD = "1y"


def _normalize_tickers(raw: list[str]) -> tuple[list[str], list[str]]:
    """
    Normaliza, valida y deduplica una lista de tickers.

    - Convierte a mayúsculas y elimina espacios.
    - Valida formato con regex (letras, dígitos, punto, caret, guion. Máx 20 chars).
    - Elimina duplicados preservando el orden original.
    - Ignora strings vacíos silenciosamente.

    Returns:
        (valid_tickers, rejected_tickers)
    """
    seen: set[str] = set()
    valid: list[str] = []
    rejected: list[str] = []

    for t in raw:
        if not isinstance(t, str):
            rejected.append(repr(t))
            continue
        normalized = t.strip().upper()
        if not normalized:
            continue
        if not _TICKER_RE.match(normalized):
            rejected.append(t)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        valid.append(normalized)

    return valid, rejected


def make_data_fetcher_node(
    market_data_service: MarketDataService,
    portfolio_service: PortfolioService,
) -> object:
    """
    Factory que construye el nodo data_fetcher del grafo LangGraph.

    Recibe los servicios necesarios por inyección de dependencias y retorna
    la función async que será registrada como nodo en el grafo.

    Args:
        market_data_service: Servicio para descargar y persistir datos OHLCV.
        portfolio_service: Servicio para registrar posiciones del usuario.
    """

    async def data_fetcher_node(state: AgentState) -> dict[str, object]:
        """
        Nodo del grafo responsable de:
        1. Persistir la posición del usuario en su portfolio (si informó ticker + cantidad + precio).
        2. Descargar y persistir datos de mercado (OHLCV) de los tickers mencionados.

        Se activa cuando el supervisor detecta la intención 'data_fetch'.
        Es un nodo blocking: se ejecuta antes que auditor o quant cuando las
        intenciones son mixtas, garantizando que los datos estén disponibles
        antes del análisis.

        Args:
            state: Estado compartido del grafo. Se leen:
                - active_tickers: lista de tickers extraídos por el supervisor
                - period: período de tiempo para la descarga de datos
                - user_id: ID del usuario de Telegram
                - quantity: cantidad de acciones informada por el usuario
                - avg_cost_usd: precio promedio de compra informado por el usuario

        Returns:
            dict con:
                - market_data_result: datos OHLCV por ticker
                - errors: lista de mensajes de error (vacía si todo ok)
        """
        raw_tickers: list[str] = state.get("active_tickers") or []
        raw_period: str = state.get("period", _DEFAULT_PERIOD) or _DEFAULT_PERIOD
        period: str = raw_period if raw_period in _VALID_PERIODS else _DEFAULT_PERIOD
        user_id: int = state.get("user_id", 0)
        positions: list[dict[str, Any]] = state.get("positions") or []

        if not raw_tickers:
            logger.warning("[DataFetcher] user=%s — no tickers in state, skipping", user_id)
            return {"market_data_result": {}, "positions": [], "errors": []}

        tickers, rejected = _normalize_tickers(raw_tickers)

        if not tickers:
            return {
                "market_data_result": {},
                "positions": [],
                "errors": [f"Los tickers no son válidos: {raw_tickers}"],
            }

        # Persistir posiciones extraídas por el supervisor LLM
        confirmed_positions: list[dict[str, Any]] = []
        position_errors: list[str] = []

        for pos in positions:
            ticker = str(pos.get("ticker", "")).upper()
            quantity = float(pos.get("quantity") or 0)
            avg_cost_usd = float(pos.get("avg_cost_usd") or 0)
            asset_type_raw = str(pos.get("asset_type") or "stock").lower()
            action = str(pos.get("action") or "buy").lower()

            if not ticker or quantity <= 0:
                logger.warning("[DataFetcher] user=%s — skipping incomplete position: %s", user_id, pos)
                continue

            if action == "sell":
                logger.info(
                    "REGISTER_POSITION user_id=%s action=sell ticker=%s quantity=%s",
                    user_id, ticker, quantity,
                )
                try:
                    portfolio = await portfolio_service.get_or_create(user_id)
                    existing = portfolio.get_position(ticker)
                    if existing is None:
                        logger.warning(
                            "[DataFetcher] user=%s — sell: no existing position for %s, nothing to reduce",
                            user_id, ticker,
                        )
                    elif Decimal(str(quantity)) >= existing.quantity:
                        await portfolio_service.remove_position(user_id, ticker)
                        logger.info(
                            "REGISTER_POSITION saved action=sell type=full ticker=%s user_id=%s",
                            ticker, user_id,
                        )
                        confirmed_positions.append(pos)
                    else:
                        new_qty = existing.quantity - Decimal(str(quantity))
                        reduce_cmd = AddPositionCommand(
                            user_id=user_id,
                            ticker=ticker,
                            asset_type=existing.asset_type,
                            quantity=new_qty,
                            avg_cost_usd=existing.avg_cost_usd,
                        )
                        await portfolio_service.add_position(reduce_cmd)
                        logger.info(
                            "REGISTER_POSITION saved action=sell type=partial ticker=%s user_id=%s",
                            ticker, user_id,
                        )
                        confirmed_positions.append(pos)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.error("[DataFetcher] user=%s — failed to process sell for %s: %s", user_id, ticker, exc)
                    position_errors.append(f"Error al procesar venta de {ticker}: {exc}")
            else:
                if avg_cost_usd <= 0:
                    logger.warning("[DataFetcher] user=%s — skipping buy without price: %s", user_id, pos)
                    continue
                logger.info(
                    "REGISTER_POSITION user_id=%s action=buy ticker=%s quantity=%s avg_cost_usd=%s",
                    user_id, ticker, quantity, avg_cost_usd,
                )
                try:
                    try:
                        asset_type = AssetType(asset_type_raw)
                    except ValueError:
                        logger.warning(
                            "[DataFetcher] user=%s — unknown asset_type %r for %s, defaulting to stock",
                            user_id, asset_type_raw, ticker,
                        )
                        asset_type = AssetType.STOCK
                    add_cmd = AddPositionCommand(
                        user_id=user_id,
                        ticker=ticker,
                        asset_type=asset_type,
                        quantity=Decimal(str(quantity)),
                        avg_cost_usd=Decimal(str(avg_cost_usd)),
                    )
                    await portfolio_service.add_position(add_cmd)
                    logger.info("REGISTER_POSITION saved action=buy ticker=%s user_id=%s", ticker, user_id)
                    confirmed_positions.append(pos)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.error("[DataFetcher] user=%s — failed to save position %s: %s", user_id, ticker, exc)
                    position_errors.append(f"Error al registrar {ticker}: {exc}")

        # Descargar y persistir datos de mercado
        try:
            fetch_cmd = FetchMarketDataCommand(tickers=tickers, period=period)
            ohlcv_by_ticker = await market_data_service.fetch_and_persist(fetch_cmd)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(
                "[DataFetcher] user=%s — MarketDataService raised: %s",
                user_id,
                exc,
                exc_info=True,
            )
            return {
                "market_data_result": {},
                "positions": confirmed_positions,
                "errors": position_errors + [f"Error al obtener datos de mercado: {exc}"],
            }

        result: dict[str, object] = {}
        successful: list[str] = []
        failed: list[str] = []

        for ticker, records in ohlcv_by_ticker.items():
            if records:
                result[ticker] = {
                    "ok": True,
                    "records_count": len(records),
                    "latest_close": float(records[-1].close),
                    "first_close": float(records[0].close),
                    "latest_date": records[-1].date.isoformat(),
                    "first_date": records[0].date.isoformat(),
                }
                successful.append(ticker)
            else:
                result[ticker] = {
                    "ok": False,
                    "records_count": 0,
                    "latest_close": None,
                    "first_close": None,
                    "latest_date": None,
                    "first_date": None,
                }
                failed.append(ticker)

        error_msg: str | None = None
        if not successful:
            error_msg = f"No se obtuvieron datos para ningún ticker: {failed}."
        elif failed:
            error_msg = f"Sin datos para: {failed}. Descargados correctamente: {successful}."

        if rejected:
            rejected_note = f" Tickers con formato inválido ignorados: {rejected}."
            error_msg = (error_msg + rejected_note) if error_msg else rejected_note

        all_errors = position_errors + ([error_msg] if error_msg else [])
        return {
            "market_data_result": result,
            "positions": confirmed_positions,
            "errors": all_errors,
        }

    return data_fetcher_node
