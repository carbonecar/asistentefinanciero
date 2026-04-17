import logging

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from financial_assistant.agents.auditor.agent import make_auditor_node
from financial_assistant.agents.data_fetcher.agent import make_data_fetcher_node
from financial_assistant.agents.fx_fetcher.agent import make_fx_fetcher_node
from financial_assistant.agents.news_scout.agent import make_news_scout_node
from financial_assistant.agents.quant.agent import make_quant_node
from financial_assistant.agents.state import AgentState, NODE_FOR_INTENT, Node
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


def route_by_intent(state: AgentState) -> list[str]:
    intents = state.get("intents", [Node.UNSUPPORTED])
    destinations= [NODE_FOR_INTENT.get(intent, Node.UNSUPPORTED) for intent in intents]
    logger.info("[GRAPH] supervisor → %s (intents=%s, tickers=%s)", destinations, intents, state.get("active_tickers"))
    return destinations


def build_graph(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    audit_service: object,
    market_data_service: object,
    quant_service: object,
    news_service: object,
    fx_gateway: object,
    llm_provider: str = "openai",
    llm_model: str = "gpt-4o-mini",
    llm_api_key: str = "",
    llm_base_url: str = "http://localhost:11434",
) -> object:
    workflow = StateGraph(AgentState)

    llm_kwargs = dict(provider=llm_provider, model=llm_model, api_key=llm_api_key, base_url=llm_base_url)

    # Register nodes
    workflow.add_node(Node.SUPERVISOR, make_supervisor_node(**llm_kwargs))
    workflow.add_node(Node.DATA_FETCHER, make_data_fetcher_node(market_data_service))  # type: ignore[arg-type]
    workflow.add_node(Node.AUDITOR, make_auditor_node(audit_service))  # type: ignore[arg-type]
    workflow.add_node(Node.QUANT, make_quant_node(quant_service))  # type: ignore[arg-type]
    workflow.add_node(Node.NEWS_SCOUT, make_news_scout_node(news_service))  # type: ignore[arg-type]
    workflow.add_node(Node.FX_FETCHER, make_fx_fetcher_node(fx_gateway))  # type: ignore[arg-type]
    workflow.add_node(Node.UX_AGENT, make_ux_node(**llm_kwargs))
    workflow.add_node(Node.UNSUPPORTED, unsupported_node)

    # Entry point
    workflow.set_entry_point(Node.SUPERVISOR)

    # Route from supervisor to specialists
    workflow.add_conditional_edges(
        Node.SUPERVISOR,
        route_by_intent,
        {
            Node.DATA_FETCHER: Node.DATA_FETCHER,
            Node.AUDITOR: Node.AUDITOR,
            Node.QUANT: Node.QUANT,
            Node.NEWS_SCOUT: Node.NEWS_SCOUT,
            Node.UX_AGENT: Node.FX_FETCHER,  # general intent: skip specialists, go to fx then ux
            Node.UNSUPPORTED: Node.UNSUPPORTED,
        },
    )

    # All specialists converge to fx_fetcher, then ux_agent
    for node in (Node.DATA_FETCHER, Node.AUDITOR, Node.QUANT, Node.NEWS_SCOUT):
        workflow.add_edge(node, Node.FX_FETCHER)

    workflow.add_edge(Node.FX_FETCHER, Node.UX_AGENT)
    workflow.add_edge(Node.UX_AGENT, END)
    workflow.add_edge(Node.UNSUPPORTED, END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
