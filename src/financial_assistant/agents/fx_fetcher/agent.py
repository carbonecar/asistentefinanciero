import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.domain.ports.fx_gateway import IExchangeRateGateway

logger = logging.getLogger(__name__)


def make_fx_fetcher_node(fx_gateway: IExchangeRateGateway):  # type: ignore[no-untyped-def]
    async def fx_fetcher_node(state: AgentState) -> dict:
        try:
            rates = await fx_gateway.fetch_rates()
            logger.info("[FX] fetched %d rates. State: %s", len(rates), state)
            return {"exchange_rates": rates, "error": None}
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("FX fetcher failed: %s", exc)
            return {"exchange_rates": [], "error": None}  # non-fatal

    return fx_fetcher_node
