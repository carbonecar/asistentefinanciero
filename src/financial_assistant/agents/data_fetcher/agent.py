import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import FetchMarketDataCommand
from financial_assistant.application.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


def make_data_fetcher_node(market_data_service: MarketDataService):  # type: ignore[no-untyped-def]
    async def data_fetcher_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        tickers = state.get("active_tickers") or []
        period = state.get("period", "1y")

        if not tickers:
            return {"market_data_result": {}, "error": None}

        try:
            cmd = FetchMarketDataCommand(tickers=tickers, period=period)
            ohlcv_by_ticker = await market_data_service.fetch_and_persist(cmd)
            # Serialize to a JSON-compatible summary for downstream agents
            result = {
                ticker: {
                    "records_count": len(records),
                    "latest_close": float(records[-1].close) if records else None,
                    "first_close": float(records[0].close) if records else None,
                }
                for ticker, records in ohlcv_by_ticker.items()
            }
            return {"market_data_result": result, "error": None}
        except Exception as exc:
            logger.error("DataFetcher failed: %s", exc)
            return {"market_data_result": {}, "error": str(exc)}

    return data_fetcher_node
