import logging
import traceback

from langchain_core.messages import SystemMessage

from financial_assistant.agents.llm_factory import make_llm
from financial_assistant.agents.state import VALID_INTENTS, AgentState
from financial_assistant.agents.supervisor.prompts import CLASSIFY_INTENT_SCHEMA, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def make_supervisor_node(  # type: ignore[no-untyped-def]
    model: str,
    api_key: str = "",
    provider: str = "openai",
    base_url: str = "http://localhost:11434",
):
    llm = make_llm(provider=provider, model=model, temperature=0, api_key=api_key, base_url=base_url)
    llm_with_tools = llm.bind_tools([{"type": "function", "function": CLASSIFY_INTENT_SCHEMA}])

    async def supervisor_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        """
        Agente supervisor que clasifica la intención del usuario y extrae entidades.
        Devuelve un diccionario con las claves:
        - "intents": lista de intenciones clasificadas (ejemplo: ["audit", "news"])
        - "active_tickers": lista de tickers activos (ejemplo: ["AAPL", "GD30"])
        - "period": período de tiempo mencionado (ejemplo: "1y", "6mo", "3mo")
        - "use_sentiment": indica si el usuario quiere optimización ajustada por sentimiento
        """
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        try:
            response = await llm_with_tools.ainvoke(messages)
            tool_calls = getattr(response, "tool_calls", [])
            if tool_calls:
                args = tool_calls[0]["args"]
                raw = args.get("intents", ["general"])
                intents = [i for i in raw if i in VALID_INTENTS]
                if not intents:
                    logger.warning("Supervisor returned no valid intents from %r, defaulting to ['general']", raw)
                    intents = ["general"]
                return {
                    "intents": intents,
                    "active_tickers": [t.upper() for t in args.get("tickers", [])],
                    "period": args.get("period", "1y"),
                    "use_sentiment": args.get("use_sentiment", False),
                }
        except Exception:
            logger.error("Supervisor LLM call failed — routing to 'general':\n%s", traceback.format_exc())

        return {
            "intents": ["general"],
            "active_tickers": [],
            "period": "1y",
            "use_sentiment": False,
        }

    return supervisor_node
