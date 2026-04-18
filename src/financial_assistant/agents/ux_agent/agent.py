import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from financial_assistant.agents.llm_factory import make_llm
from financial_assistant.agents.state import AgentState
from financial_assistant.agents.ux_agent.prompts import SYNTHESIS_SYSTEM_PROMPT, SYNTHESIS_USER_TEMPLATE

logger = logging.getLogger(__name__)

_MAX_HISTORY = 10  # últimos N mensajes para no crecer infinito


def make_ux_node(  # type: ignore[no-untyped-def]
    model: str,
    api_key: str = "",
    provider: str = "openai",
    base_url: str = "http://localhost:11434",
):
    llm = make_llm(provider=provider, model=model, temperature=0.3, api_key=api_key, base_url=base_url)

    async def ux_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        data_summary = _build_data_summary(state)
        user_message = state.get("user_message", "")

        # Historial reciente (excluye el último HumanMessage, que ya está en el prompt)
        history = list(state.get("messages", []))[-_MAX_HISTORY:-1]

        # El mensaje final incluye los datos disponibles como contexto
        current_prompt = SYNTHESIS_USER_TEMPLATE.format(
            user_message=user_message,
            data_summary=data_summary,
        )

        messages = [SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT)] + history + [HumanMessage(content=current_prompt)]

        try:
            response = await llm.ainvoke(messages)
            # Guardar la respuesta en el historial para turnos futuros
            return {
                "final_response": response.content,
                "messages": [AIMessage(content=response.content)],
                "error": None,
            }
        except Exception as exc:
            logger.error("UX agent LLM call failed: %s", exc)
            return {
                "final_response": "Lo siento, hubo un error al procesar tu consulta. Por favor intenta nuevamente.",
                "error": str(exc),
            }

    return ux_node


def _build_data_summary(state: AgentState) -> str:
    parts: list[str] = []

    if state.get("audit_report"):
        report = state["audit_report"]
        parts.append(f"AUDIT REPORT (period: {report.period_label}):")
        parts.append(f"  Portfolio return: {float(report.portfolio_return):.2%}")
        for comp in report.comparisons:
            parts.append(
                f"  vs {comp.benchmark_name}: {float(comp.benchmark_return):.2%} "
                f"(opportunity cost: {float(comp.opportunity_cost):+.2%})"
            )
        if report.top_performer:
            parts.append(f"  Top performer: {report.top_performer}")
        if report.worst_performer:
            parts.append(f"  Worst performer: {report.worst_performer}")

    if state.get("quant_result"):
        qr = state["quant_result"]
        if qr.optimized_weights:
            w = qr.optimized_weights
            parts.append("OPTIMIZED PORTFOLIO:")
            for ticker, weight in w.weights.items():
                if weight > 0.001:
                    parts.append(f"  {ticker}: {weight:.1%}")
            parts.append(f"  Expected return: {w.expected_annual_return:.2%}")
            parts.append(f"  Volatility: {w.annual_volatility:.2%}")
            parts.append(f"  Sharpe ratio: {w.sharpe_ratio:.2f}")
        if qr.simulation and qr.simulation.percentile_50:
            sim = qr.simulation
            final_median = sim.percentile_50[-1]
            final_p5 = sim.percentile_5[-1]
            final_p95 = sim.percentile_95[-1]
            parts.append(
                f"PROJECTION ({sim.horizon_days} days): "
                f"Median ${final_median:,.0f} | "
                f"Pessimistic ${final_p5:,.0f} | "
                f"Optimistic ${final_p95:,.0f}"
            )

    if state.get("news_results"):
        parts.append("NEWS SENTIMENT:")
        for result in state["news_results"]:
            parts.append(
                f"  {result.ticker}: {result.label} (score: {result.score:+.3f}, {result.article_count} articles)"
            )
            for headline in result.representative_headlines:
                parts.append(f"    - {headline}")

    if state.get("market_data_result"):
        md = state["market_data_result"]
        parts.append("MARKET DATA FETCHED:")
        for ticker, info in md.items():
            if info.get("latest_close"):
                parts.append(f"  {ticker}: ${info['latest_close']:.2f} ({info['records_count']} records)")

    if state.get("exchange_rates"):
        parts.append("TIPO DE CAMBIO USD/ARS (dolarapi.com):")
        for rate in state["exchange_rates"]:
            parts.append(
                f"  {rate.nombre}: compra ${rate.compra:,.2f} | venta ${rate.venta:,.2f}"
                f"  (actualizado: {rate.updated_at.strftime('%d/%m %H:%M')})"
            )

    if not parts:
        parts.append("No specific financial data available for this query.")

    return "\n".join(parts)
