import logging
from collections.abc import Hashable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from financial_assistant.agents.auditor.agent import make_auditor_node
from financial_assistant.agents.data_fetcher.agent import make_data_fetcher_node
from financial_assistant.agents.fx_fetcher.agent import make_fx_fetcher_node
from financial_assistant.agents.news_scout.agent import make_news_scout_node
from financial_assistant.agents.quant.agent import make_quant_node
from financial_assistant.agents.state import (
    BLOCKING_INTENTS,
    NODE_FOR_INTENT,
    ROUTING_OVERRIDES,
    AgentState,
    Intent,
    Node,
)
from financial_assistant.agents.supervisor.agent import make_supervisor_node
from financial_assistant.agents.ux_agent.agent import make_ux_node
from financial_assistant.application.services.audit_service import AuditService
from financial_assistant.application.services.market_data_service import MarketDataService
from financial_assistant.application.services.news_service import NewsService
from financial_assistant.application.services.portfolio_service import PortfolioService
from financial_assistant.application.services.quant_service import QuantService
from financial_assistant.domain.ports.fx_gateway import IExchangeRateGateway

logger = logging.getLogger(__name__)

UNSUPPORTED_RESPONSE = (
    "Solo puedo ayudarte con:\n"
    "• 📊 *Auditar* tu cartera\n"
    "• ⚡ *Optimizar* tu portfolio\n"
    "• 📰 *Noticias* y sentimiento de mercado\n"
    "• ➕ *Agregar posiciones* a tu cartera"
)


async def unsupported_node(state: AgentState) -> dict:  # type: ignore[type-arg]
    """
    Nodo terminal para intenciones no soportadas.

    Se activa cuando el supervisor detecta que el mensaje del usuario
    no tiene relación con finanzas o inversiones. Retorna una respuesta
    fija informando al usuario qué funcionalidades están disponibles.

    Args:
        state: Estado compartido del grafo.

    Returns:
        dict con final_response fijo y lista de errores vacía.
    """
    logger.info("[GRAPH] unsupported → END. State: %s", state)
    return {"final_response": UNSUPPORTED_RESPONSE, "errors": []}


def _resolve(intent: str) -> str:
    """
    Resuelve el nodo destino para una intención dada.

    Primero busca el nodo lógico en NODE_FOR_INTENT. Luego aplica
    ROUTING_OVERRIDES para casos especiales (ej: 'general' que debe
    pasar por fx_fetcher antes de ux_agent).

    Args:
        intent: Nombre de la intención clasificada por el supervisor.

    Returns:
        Nombre del nodo destino en el grafo.
    """
    node: str = NODE_FOR_INTENT.get(intent, Node.UNSUPPORTED)
    result: str = ROUTING_OVERRIDES.get(node, node)
    return result


def _resolve_destination(intent: str, use_sentiment: bool) -> str:
    """
    Resuelve el nodo destino para una intención, teniendo en cuenta si el
    sentimiento está activo. Cuando optimize+use_sentiment=True, se enruta
    a news_scout para que corra antes que quant y popule news_results.
    """
    if intent == "optimize" and use_sentiment:
        return Node.NEWS_SCOUT
    return _resolve(intent)


def route_by_intent(state: AgentState) -> list[str]:
    """
    Función de routing condicional que determina a qué nodo(s) derivar
    el flujo luego del supervisor.

    Separa las intenciones en dos grupos:
    - blocking: intenciones que deben ejecutarse primero (actualmente solo 'data_fetch')
    - non_blocking: el resto de las intenciones

    Si hay intenciones de ambos tipos, ejecuta primero solo los blockers.
    El post_fetch_router se encargará de despachar los non_blocking una vez
    que los blockers hayan completado.

    Si todas las intenciones son del mismo tipo, las despacha todas directamente.
    Cuando optimize+use_sentiment=True, enruta a news_scout primero para que
    sentiment_router pueda derivar a quant con news_results ya populados.

    Args:
        state: Estado compartido del grafo.

    Returns:
        Lista de nodos destino a los que derivar el flujo.
    """
    intents: list[Intent] = state.get("intents") or ["unsupported"]
    use_sentiment: bool = state.get("use_sentiment", False)
    blocking = [i for i in intents if i in BLOCKING_INTENTS]
    non_blocking = [i for i in intents if i not in BLOCKING_INTENTS]
    if blocking and non_blocking:
        destinations = [_resolve(i) for i in blocking]
    else:
        seen: set[str] = set()
        destinations = []
        for i in intents:
            if i == "optimize" and use_sentiment:
                # Dos optimizaciones en paralelo: con sentimiento (vía news_scout) y sin sentimiento
                for dest in (Node.NEWS_SCOUT, Node.QUANT_NO_SENTIMENT):
                    if dest not in seen:
                        seen.add(dest)
                        destinations.append(dest)
            else:
                dest = _resolve_destination(i, use_sentiment)
                if dest not in seen:
                    seen.add(dest)
                    destinations.append(dest)
    logger.info("[GRAPH] supervisor → %s (intents=%s, tickers=%s)", destinations, intents, state.get("active_tickers"))
    return destinations


def route_after_news_scout(state: AgentState) -> str:
    """
    Routing desde sentiment_router: si optimize está en los intents y
    use_sentiment=True, deriva a quant (que ya puede leer news_results).
    Caso contrario, va directo a fx_fetcher.
    """
    intents = state.get("intents") or []
    if "optimize" in intents and state.get("use_sentiment", False):
        return Node.QUANT
    return Node.FX_FETCHER


def post_fetch_route(state: AgentState) -> list[str]:
    """
    Función de routing condicional ejecutada luego del data_fetcher.

    Despacha las intenciones non_blocking que quedaron pendientes mientras
    el data_fetcher (blocking) se ejecutaba. Si no hay intenciones pendientes,
    deriva directamente al fx_fetcher para continuar hacia el ux_agent.
    Aplica la misma lógica de optimize+use_sentiment que route_by_intent.

    Args:
        state: Estado compartido del grafo.

    Returns:
        Lista de nodos destino pendientes, o [fx_fetcher] si no hay ninguno.
    """
    intents = state.get("intents", [])
    use_sentiment: bool = state.get("use_sentiment", False)
    seen: set[str] = set()
    remaining: list[str] = []
    for i in intents:
        if i in BLOCKING_INTENTS:
            continue
        if i == "optimize" and use_sentiment:
            for dest in (Node.NEWS_SCOUT, Node.QUANT_NO_SENTIMENT):
                if dest not in seen:
                    seen.add(dest)
                    remaining.append(dest)
            continue
        dest = _resolve_destination(i, use_sentiment)
        if dest not in seen:
            seen.add(dest)
            remaining.append(dest)
    destinations = remaining or [Node.FX_FETCHER]
    logger.info("[GRAPH] post_fetch_router → %s", destinations)
    return destinations


def build_graph(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    audit_service: AuditService,
    market_data_service: MarketDataService,
    portfolio_service: PortfolioService,
    quant_service: QuantService,
    news_service: NewsService,
    fx_gateway: IExchangeRateGateway,
    llm_provider: str = "openai",
    llm_model: str = "gpt-4o-mini",
    llm_api_key: str = "",
    llm_base_url: str = "http://localhost:11434",
) -> object:
    """
    Construye y compila el grafo de agentes LangGraph.

    Registra todos los nodos del sistema, define las aristas (edges) y
    las condiciones de routing entre ellos. El grafo resultante es el
    motor de orquestación del asistente financiero.

    Flujo general:
        supervisor → [routing condicional por intención]
            → data_fetcher → post_fetch_router → [intenciones pendientes]
            → auditor / quant / news_scout → fx_fetcher → ux_agent → END
            → unsupported → END

    Args:
        audit_service: Servicio de auditoría de portfolio.
        market_data_service: Servicio de descarga de datos de mercado.
        portfolio_service: Servicio de gestión de posiciones del usuario.
        quant_service: Servicio de optimización cuantitativa.
        news_service: Servicio de noticias y análisis de sentimiento.
        fx_gateway: Gateway para obtener tipos de cambio USD/ARS.
        llm_provider: Proveedor del LLM ('openai' u 'ollama').
        llm_model: Nombre del modelo a utilizar.
        llm_api_key: API key del proveedor (requerida para OpenAI).
        llm_base_url: URL base para Ollama.

    Returns:
        Grafo compilado listo para ser invocado con .ainvoke().
    """
    workflow = StateGraph(AgentState)

    llm_kwargs = dict(provider=llm_provider, model=llm_model, api_key=llm_api_key, base_url=llm_base_url)

    # Registro de nodos
    workflow.add_node(Node.SUPERVISOR, make_supervisor_node(**llm_kwargs))
    workflow.add_node(Node.DATA_FETCHER, make_data_fetcher_node(market_data_service, portfolio_service))  # type: ignore[call-overload]
    workflow.add_node(Node.AUDITOR, make_auditor_node(audit_service))
    workflow.add_node(Node.QUANT, make_quant_node(quant_service))  # type: ignore[call-overload]
    workflow.add_node(
        Node.QUANT_NO_SENTIMENT,
        make_quant_node(quant_service, result_key="quant_result_no_sentiment", force_no_sentiment=True),  # type: ignore[call-overload]
    )
    workflow.add_node(Node.NEWS_SCOUT, make_news_scout_node(news_service, portfolio_service))  # type: ignore[call-overload]
    workflow.add_node(Node.FX_FETCHER, make_fx_fetcher_node(fx_gateway))
    workflow.add_node(Node.UX_AGENT, make_ux_node(**llm_kwargs))
    workflow.add_node(Node.UNSUPPORTED, unsupported_node)
    workflow.add_node(
        Node.POST_FETCH_ROUTER, lambda _: {}
    )  # nodo de enrutamiento sin procesamiento, solo para decidir el siguiente paso después de data_fetcher
    workflow.add_node(Node.SENTIMENT_ROUTER, lambda _: {})

    # Punto de entrada
    workflow.set_entry_point(Node.SUPERVISOR)

    _specialist_map: dict[Hashable, str] = {
        Node.DATA_FETCHER: Node.DATA_FETCHER,
        Node.AUDITOR: Node.AUDITOR,
        Node.QUANT: Node.QUANT,
        Node.QUANT_NO_SENTIMENT: Node.QUANT_NO_SENTIMENT,
        Node.NEWS_SCOUT: Node.NEWS_SCOUT,
        Node.FX_FETCHER: Node.FX_FETCHER,
        Node.UNSUPPORTED: Node.UNSUPPORTED,
    }

    workflow.add_conditional_edges(Node.SUPERVISOR, route_by_intent, _specialist_map)

    # data_fetcher siempre va a post_fetch_router para despachar intenciones pendientes
    workflow.add_edge(Node.DATA_FETCHER, Node.POST_FETCH_ROUTER)
    workflow.add_conditional_edges(Node.POST_FETCH_ROUTER, post_fetch_route, _specialist_map)

    # auditor, quant y quant_no_sentiment convergen en fx_fetcher
    for node in (Node.AUDITOR, Node.QUANT, Node.QUANT_NO_SENTIMENT):
        workflow.add_edge(node, Node.FX_FETCHER)

    # news_scout siempre pasa por sentiment_router, que decide si continúa a quant o fx_fetcher
    workflow.add_edge(Node.NEWS_SCOUT, Node.SENTIMENT_ROUTER)
    workflow.add_conditional_edges(
        Node.SENTIMENT_ROUTER,
        route_after_news_scout,
        {Node.QUANT: Node.QUANT, Node.FX_FETCHER: Node.FX_FETCHER},
    )

    workflow.add_edge(Node.FX_FETCHER, Node.UX_AGENT)
    workflow.add_edge(Node.UX_AGENT, END)
    workflow.add_edge(Node.UNSUPPORTED, END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
