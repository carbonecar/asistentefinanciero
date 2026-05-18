import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.domain.ports.fx_gateway import IExchangeRateGateway

logger = logging.getLogger(__name__)


def make_fx_fetcher_node(fx_gateway: IExchangeRateGateway):  # type: ignore[no-untyped-def]
    async def fx_fetcher_node(state: AgentState) -> dict[str, object]:
        try:
            rates = await fx_gateway.fetch_rates()
            logger.info("FX_FETCHER rates_count=%d labels=%s", len(rates), [r.casa for r in rates])
            return {"exchange_rates": rates, "errors": []}
        except Exception as exc:
            logger.warning("FX fetcher failed: %s", exc)
            return {"exchange_rates": [], "errors": []}  # non-fatal

    return fx_fetcher_node
