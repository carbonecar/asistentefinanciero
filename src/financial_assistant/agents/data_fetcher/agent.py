import logging
import re
from datetime import date
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

# Validación de purchase_date: protege contra alucinación del LLM (fechas inventadas).
# Si el modelo devuelve una fecha futura o irrazonablemente vieja, la rechazamos
# antes de persistir y pedimos aclaración al usuario.
_MAX_PURCHASE_AGE_DAYS = 365 * 30  # 30 años hacia atrás


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


def _validate_purchase_date(purchase_date: date, today: date) -> str | None:
    """
    Valida que purchase_date sea razonable.

    Returns:
        None si la fecha es válida, o un mensaje de error describiendo el problema.
    """
    if purchase_date > today:
        return f"fecha futura ({purchase_date.isoformat()})"
    if (today - purchase_date).days > _MAX_PURCHASE_AGE_DAYS:
        return f"fecha demasiado antigua ({purchase_date.isoformat()})"
    return None


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
                - pending_positions: posiciones esperando confirmación de precio histórico
                - errors: lista de mensajes de error (vacía si todo ok)
        """
        raw_tickers: list[str] = state.get("active_tickers") or []
        raw_period: str = state.get("period", _DEFAULT_PERIOD) or _DEFAULT_PERIOD
        period: str = raw_period if raw_period in _VALID_PERIODS else _DEFAULT_PERIOD
        user_id: int = state.get("user_id", 0)
        positions: list[dict[str, Any]] = state.get("positions") or []

        # Si no hay posiciones nuevas pero hay pending_positions, es una confirmación directa
        # El usuario ya aprobó el precio — registrar sin pasar por el supervisor
        pending_in_state = state.get("pending_positions") or []
        if not positions and pending_in_state:
            logger.info(
                "[DataFetcher] user=%s — direct confirmation, registering %d pending positions",
                user_id,
                len(pending_in_state),
            )
            today = date.today()
            confirmed_invalid: list[dict[str, str]] = []
            for p in pending_in_state:
                try:
                    p_date = date.fromisoformat(p["purchase_date"])
                except (ValueError, KeyError, TypeError) as exc:
                    logger.error(
                        "[DataFetcher] user=%s — invalid purchase_date in pending %s: %s",
                        user_id,
                        p.get("ticker"),
                        exc,
                    )
                    confirmed_invalid.append({"ticker": p.get("ticker", "?"), "reason": "fecha mal formada"})
                    continue

                invalid_reason = _validate_purchase_date(p_date, today)
                if invalid_reason:
                    logger.warning(
                        "[DataFetcher] user=%s — rejecting pending %s due to %s",
                        user_id,
                        p["ticker"],
                        invalid_reason,
                    )
                    confirmed_invalid.append({"ticker": p["ticker"], "reason": invalid_reason})
                    continue

                try:
                    add_cmd = AddPositionCommand(
                        user_id=user_id,
                        ticker=p["ticker"],
                        asset_type=AssetType(p["asset_type"]),
                        quantity=Decimal(str(p["quantity"])),
                        avg_cost_usd=Decimal(str(p["suggested_price"])),
                        purchase_date=p_date,
                    )
                    await portfolio_service.add_position(add_cmd)
                    logger.info(
                        "[DataFetcher] user=%s — confirmed position saved: %s x%s @ $%s",
                        user_id,
                        p["ticker"],
                        p["quantity"],
                        p["suggested_price"],
                    )
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.error(
                        "[DataFetcher] user=%s — failed to save confirmed position %s: %s", user_id, p["ticker"], exc
                    )

            errors: list[str] = []
            if confirmed_invalid:
                errors.append(
                    "Posiciones pendientes rechazadas por fecha inválida — el usuario debe "
                    "re-indicar la fecha completa (día, mes y año): "
                    + ", ".join(f"{d['ticker']} ({d['reason']})" for d in confirmed_invalid)
                    + "."
                )
            return {
                "market_data_result": {},
                "pending_positions": [],
                "errors": errors,
            }

        if not raw_tickers:
            logger.warning("[DataFetcher] user=%s — no tickers in state, skipping", user_id)
            return {"market_data_result": {}, "pending_positions": [], "errors": []}

        tickers, rejected = _normalize_tickers(raw_tickers)

        if not tickers:
            return {
                "market_data_result": {},
                "pending_positions": [],
                "errors": [f"Los tickers no son válidos: {raw_tickers}"],
            }

        # Precios sugeridos de pending_positions del turno anterior (confirmación del usuario)
        pending_in_state = state.get("pending_positions") or []
        confirmed_prices = {p["ticker"]: p["suggested_price"] for p in pending_in_state}

        # Persistir posiciones extraídas por el supervisor LLM
        pending_positions: list[dict[str, Any]] = []
        invalid_dates: list[dict[str, str]] = []  # posiciones rechazadas por fecha inválida (alucinación del LLM)
        missing_dates: list[str] = []  # tickers sin fecha de compra — el ux_agent debe pedirla

        for pos in positions:
            ticker = str(pos.get("ticker", "")).upper()
            quantity = float(pos.get("quantity") or 0)
            avg_cost_usd = float(pos.get("avg_cost_usd") or 0)
            asset_type_raw = str(pos.get("asset_type") or "stock")
            purchase_date_raw = pos.get("purchase_date")
            purchase_date = date.fromisoformat(purchase_date_raw) if purchase_date_raw else None

            if not ticker or quantity <= 0:
                logger.warning("[DataFetcher] user=%s — skipping incomplete position: %s", user_id, pos)
                continue

            # Sin fecha de compra no se puede registrar — el ux_agent debe pedirla
            if not purchase_date:
                logger.warning("[DataFetcher] user=%s — skipping %s: missing purchase_date", user_id, ticker)
                missing_dates.append(ticker)
                continue

            # Validación defensiva contra alucinación de fecha por parte del LLM
            invalid_reason = _validate_purchase_date(purchase_date, date.today())
            if invalid_reason:
                logger.warning(
                    "[DataFetcher] user=%s — rejecting %s due to %s",
                    user_id, ticker, invalid_reason,
                )
                invalid_dates.append({"ticker": ticker, "reason": invalid_reason})
                continue

            # Con fecha — buscar precio histórico y proponer al usuario
            if ticker in confirmed_prices:
                # Ya fue confirmado en turno anterior, usar el precio sugerido
                avg_cost_usd = confirmed_prices[ticker]
                logger.info(
                    "[DataFetcher] user=%s — using confirmed historical price for %s: $%s",
                    user_id,
                    ticker,
                    avg_cost_usd,
                )
            else:
                # Primera vez — buscar precio histórico y poner en pending
                historical_price = await market_data_service.get_price_at_date(ticker, purchase_date)
                if historical_price:
                    pending = {
                        "ticker": ticker,
                        "quantity": quantity,
                        "asset_type": asset_type_raw,
                        "purchase_date": purchase_date_raw,
                        "suggested_price": historical_price,
                    }
                    pending_positions.append(pending)
                    continue

            try:
                add_cmd = AddPositionCommand(
                    user_id=user_id,
                    ticker=ticker,
                    asset_type=AssetType(asset_type_raw),
                    quantity=Decimal(str(quantity)),
                    avg_cost_usd=Decimal(str(avg_cost_usd)),
                    purchase_date=purchase_date,
                )
                await portfolio_service.add_position(add_cmd)
                logger.info(
                    "[DataFetcher] user=%s — position saved: %s x%s @ $%s", user_id, ticker, quantity, avg_cost_usd
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.error("[DataFetcher] user=%s — failed to save position %s: %s", user_id, ticker, exc)

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
                "pending_positions": pending_positions,
                "errors": [f"Error al obtener datos de mercado: {exc}"],
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

        if invalid_dates:
            dates_note = (
                " Posiciones rechazadas por fecha inválida — el usuario debe "
                "re-indicar la fecha completa (día, mes y año): "
                + ", ".join(f"{d['ticker']} ({d['reason']})" for d in invalid_dates)
                + "."
            )
            error_msg = (error_msg + dates_note) if error_msg else dates_note

        if missing_dates:
            missing_note = (
                " Posiciones NO registradas por falta de fecha de compra completa "
                "(día, mes y año) — pedirla al usuario antes de registrar: "
                + ", ".join(missing_dates)
                + "."
            )
            error_msg = (error_msg + missing_note) if error_msg else missing_note

        return {
            "market_data_result": result,
            "pending_positions": pending_positions,
            "errors": [error_msg] if error_msg else [],
        }

    return data_fetcher_node
