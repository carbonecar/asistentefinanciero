import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.domain.ports.fx_gateway import IExchangeRateGateway

logger = logging.getLogger(__name__)


def make_fx_fetcher_node(fx_gateway: IExchangeRateGateway):  # type: ignore[no-untyped-def]
    async def fx_fetcher_node(state: AgentState) -> dict[str, object]:
        # NOTA: no retornamos "errors" en ningún caso.
        # Este nodo es non-fatal (su fallo no debe romper la cadena) y no
        # genera errores propios que el ux_agent deba mostrar. Retornar
        # "errors: []" pisaría los errores del data_fetcher, que llegan
        # al ux_agent vía el state y guían su respuesta al usuario.
        try:
            rates = await fx_gateway.fetch_rates()
            logger.info("[FX] fetched %d rates. State: %s", len(rates), state)
            return {"exchange_rates": rates}
        except Exception as exc:
            logger.warning("FX fetcher failed: %s", exc)
            return {"exchange_rates": []}

    return fx_fetcher_node