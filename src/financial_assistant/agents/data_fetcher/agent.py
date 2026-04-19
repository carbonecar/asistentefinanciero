import logging
import re

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import FetchMarketDataCommand
from financial_assistant.application.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)

# Tickers válidos: letras, dígitos, punto (GGAL.BA), caret (^GSPC), guion (BRK-B). Máx 20 chars.
_TICKER_RE = re.compile(r'^[\w.\^\-]{1,20}$')

_VALID_PERIODS: frozenset[str] = frozenset({
    "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max",
})
_DEFAULT_PERIOD = "1y"


def _normalize_tickers(raw: list[str]) -> tuple[list[str], list[str]]:
    """Uppercase, strip, deduplicate and validate tickers.

    Returns (valid_tickers, rejected_tickers).
    Preserves original order. Silently drops empty strings after strip.
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
            continue  # deduplicate silently
        seen.add(normalized)
        valid.append(normalized)

    return valid, rejected


def make_data_fetcher_node(market_data_service: MarketDataService):  # type: ignore[no-untyped-def]
    async def data_fetcher_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        raw_tickers: list[str] = state.get("active_tickers") or []
        raw_period: str = state.get("period", _DEFAULT_PERIOD) or _DEFAULT_PERIOD
        period = raw_period if raw_period in _VALID_PERIODS else _DEFAULT_PERIOD
        if period != raw_period:
            logger.warning(
                "[DataFetcher] user=%s — invalid period %r, defaulting to %s",
                state.get("user_id"), raw_period, _DEFAULT_PERIOD,
            )
        user_id = state.get("user_id")

        if not raw_tickers:
            logger.warning("[DataFetcher] user=%s — no tickers in state, skipping", user_id)
            return {"market_data_result": {}, "errors": []}

        tickers, rejected = _normalize_tickers(raw_tickers)

        if rejected:
            logger.warning(
                "[DataFetcher] user=%s — rejected invalid tickers: %s",
                user_id, rejected,
            )

        if not tickers:
            logger.warning(
                "[DataFetcher] user=%s — all tickers invalid after normalization: %s",
                user_id, raw_tickers,
            )
            return {
                "market_data_result": {},
                "errors": [f"Los tickers no son válidos: {raw_tickers}"],
            }

        logger.info(
            "[DataFetcher] user=%s — fetching %d ticker(s): %s (period=%s)",
            user_id, len(tickers), tickers, period,
        )

        try:
            cmd = FetchMarketDataCommand(tickers=tickers, period=period)
            ohlcv_by_ticker = await market_data_service.fetch_and_persist(cmd)
        except Exception as exc:
            logger.error(
                "[DataFetcher] user=%s — MarketDataService raised: %s",
                user_id, exc, exc_info=True,
            )
            return {
                "market_data_result": {},
                "errors": [f"Error al obtener datos de mercado: {exc}"],
            }

        result: dict = {}  # type: ignore[type-arg]
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

        ba_failed = [t for t in failed if t.endswith(".BA")]
        non_ba_failed = [t for t in failed if not t.endswith(".BA")]

        if failed:
            if ba_failed:
                logger.warning(
                    "[DataFetcher] user=%s — no data for Argentine tickers: %s "
                    "(verify they are listed on BYMA and the .BA suffix is correct)",
                    user_id, ba_failed,
                )
            if non_ba_failed:
                logger.warning(
                    "[DataFetcher] user=%s — no data for: %s "
                    "(ticker may be invalid or source unavailable)",
                    user_id, non_ba_failed,
                )

        logger.info(
            "[DataFetcher] user=%s — done: %d ok, %d failed",
            user_id, len(successful), len(failed),
        )

        if not successful:
            hint = (
                f" Tickers argentinos ({ba_failed}): verificá que estén en BYMA con el sufijo .BA correcto."
                if ba_failed else ""
            )
            error_msg = f"No se obtuvieron datos para ningún ticker: {failed}.{hint}"
        elif failed:
            hint = (
                f" Tickers argentinos sin datos ({ba_failed}): verificá el sufijo .BA."
                if ba_failed else ""
            )
            error_msg = f"Sin datos para: {failed}. Descargados correctamente: {successful}.{hint}"
        else:
            error_msg = None

        if rejected:
            rejected_note = f" Tickers con formato inválido ignorados: {rejected}."
            error_msg = (error_msg + rejected_note) if error_msg else rejected_note

        return {"market_data_result": result, "errors": [error_msg] if error_msg else []}

    return data_fetcher_node
