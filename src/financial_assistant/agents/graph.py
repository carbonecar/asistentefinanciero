import logging

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from financial_assistant.agents.auditor.agent import make_auditor_node
from financial_assistant.agents.data_fetcher.agent import make_data_fetcher_node
from financial_assistant.agents.fx_fetcher.agent import make_fx_fetcher_node
from financial_assistant.agents.news_scout.agent import make_news_scout_node
from financial_assistant.agents.quant.agent import make_quant_node
from financial_assistant.agents.state import AgentState, BLOCKING_INTENTS, NODE_FOR_INTENT, Node, ROUTING_OVERRIDES
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


def _resolve(intent: str) -> str:
    node = NODE_FOR_INTENT.get(intent, Node.UNSUPPORTED)
    return ROUTING_OVERRIDES.get(node, node)


def route_by_intent(state: AgentState) -> list[str]:
    intents = state.get("intents", [Node.UNSUPPORTED])
    blocking = [i for i in intents if i in BLOCKING_INTENTS]
    non_blocking = [i for i in intents if i not in BLOCKING_INTENTS]
    if blocking and non_blocking:
        # run blockers first; post_fetch_router will dispatch the rest
        destinations = [_resolve(i) for i in blocking]
    else:
        destinations = [_resolve(i) for i in intents]
    logger.info("[GRAPH] supervisor → %s (intents=%s, tickers=%s)", destinations, intents, state.get("active_tickers"))
    return destinations


def post_fetch_route(state: AgentState) -> list[str]:
    intents = state.get("intents", [])
    remaining = [_resolve(i) for i in intents if i not in BLOCKING_INTENTS]
    destinations = remaining or [Node.FX_FETCHER]
    logger.info("[GRAPH] post_fetch_router → %s", destinations)
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
    workflow.add_node(Node.POST_FETCH_ROUTER, lambda _: {})

    # Entry point
    workflow.set_entry_point(Node.SUPERVISOR)

    _specialist_map = {
        Node.DATA_FETCHER: Node.DATA_FETCHER,
        Node.AUDITOR: Node.AUDITOR,
        Node.QUANT: Node.QUANT,
        Node.NEWS_SCOUT: Node.NEWS_SCOUT,
        Node.FX_FETCHER: Node.FX_FETCHER,  # general after data_fetch, or no remaining intents
        Node.UNSUPPORTED: Node.UNSUPPORTED,
    }

    workflow.add_conditional_edges(Node.SUPERVISOR, route_by_intent, _specialist_map)

    # data_fetcher always goes to post_fetch_router to dispatch any remaining intents
    workflow.add_edge(Node.DATA_FETCHER, Node.POST_FETCH_ROUTER)
    workflow.add_conditional_edges(Node.POST_FETCH_ROUTER, post_fetch_route, _specialist_map)

    # remaining specialists converge to fx_fetcher
    for node in (Node.AUDITOR, Node.QUANT, Node.NEWS_SCOUT):
        workflow.add_edge(node, Node.FX_FETCHER)

    workflow.add_edge(Node.FX_FETCHER, Node.UX_AGENT)
    workflow.add_edge(Node.UX_AGENT, END)
    workflow.add_edge(Node.UNSUPPORTED, END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
