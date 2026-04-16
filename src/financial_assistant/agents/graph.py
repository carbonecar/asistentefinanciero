import logging

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from financial_assistant.agents.auditor.agent import make_auditor_node
from financial_assistant.agents.data_fetcher.agent import make_data_fetcher_node
from financial_assistant.agents.news_scout.agent import make_news_scout_node
from financial_assistant.agents.quant.agent import make_quant_node
from financial_assistant.agents.state import AgentState
from financial_assistant.agents.supervisor.agent import make_supervisor_node
from financial_assistant.agents.ux_agent.agent import make_ux_node

logger = logging.getLogger(__name__)

UNSUPPORTED_RESPONSE = (
    "Solo puedo ayudarte con:\n"
    "• 📊 *Auditar* tu cartera\n"
    "• ⚡ *Optimizar* tu portfolio\n"
    "• 📰 *Noticias* y sentimiento de mercado\n"
    "• ➕ *Agregar posiciones* a tu cartera"
)


async def unsupported_node(state: AgentState) -> dict:  # type: ignore[type-arg]
    logger.info("[GRAPH] unsupported → END")
    return {"final_response": UNSUPPORTED_RESPONSE, "error": None}


def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "unsupported")
    routes = {
        "audit": "auditor",
        "optimize": "quant",
        "news": "news_scout",
        "data_fetch": "data_fetcher",
        "general": "ux_agent",
        "unsupported": "unsupported",
    }
    destination = routes.get(intent, "ux_agent")
    logger.info("[GRAPH] supervisor → %s (intent=%s, tickers=%s)", destination, intent, state.get("active_tickers"))
    return destination


def build_graph(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    audit_service: object,
    market_data_service: object,
    quant_service: object,
    news_service: object,
    llm_provider: str = "openai",
    llm_model: str = "gpt-4o-mini",
    llm_api_key: str = "",
    llm_base_url: str = "http://localhost:11434",
) -> object:
    workflow = StateGraph(AgentState)

    llm_kwargs = dict(provider=llm_provider, model=llm_model, api_key=llm_api_key, base_url=llm_base_url)

    # Register nodes
    workflow.add_node("supervisor", make_supervisor_node(**llm_kwargs))
    workflow.add_node("data_fetcher", make_data_fetcher_node(market_data_service))  # type: ignore[arg-type]
    workflow.add_node("auditor", make_auditor_node(audit_service))  # type: ignore[arg-type]
    workflow.add_node("quant", make_quant_node(quant_service))  # type: ignore[arg-type]
    workflow.add_node("news_scout", make_news_scout_node(news_service))  # type: ignore[arg-type]
    workflow.add_node("ux_agent", make_ux_node(**llm_kwargs))
    workflow.add_node("unsupported", unsupported_node)

    # Entry point
    workflow.set_entry_point("supervisor")

    # Route from supervisor to specialists
    workflow.add_conditional_edges(
        "supervisor",
        route_by_intent,
        {
            "data_fetcher": "data_fetcher",
            "auditor": "auditor",
            "quant": "quant",
            "news_scout": "news_scout",
            "ux_agent": "ux_agent",
            "unsupported": "unsupported",
        },
    )

    # All specialists converge to UX agent
    for node in ("data_fetcher", "auditor", "quant", "news_scout"):
        workflow.add_edge(node, "ux_agent")

    workflow.add_edge("ux_agent", END)
    workflow.add_edge("unsupported", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
