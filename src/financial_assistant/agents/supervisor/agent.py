import logging

from langchain_core.messages import SystemMessage

from financial_assistant.agents.llm_factory import make_llm
from financial_assistant.agents.state import AgentState
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

    _valid_intents = {"audit", "optimize", "news", "data_fetch", "general", "unsupported"}

    async def supervisor_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        try:
            response = await llm_with_tools.ainvoke(messages)
            tool_calls = getattr(response, "tool_calls", [])
            if tool_calls:
                args = tool_calls[0]["args"]
                intent = args.get("intent", "general")
                if intent not in _valid_intents:
                    logger.warning("Supervisor returned unknown intent %r, defaulting to 'general'", intent)
                    intent = "general"
                return {
                    "intent": intent,
                    "active_tickers": [t.upper() for t in args.get("tickers", [])],
                    "period": args.get("period", "1y"),
                    "use_sentiment": args.get("use_sentiment", False),
                }
        except Exception as exc:
            logger.warning("Supervisor LLM call failed: %s", exc)

        return {
            "intent": "general",
            "active_tickers": [],
            "period": "1y",
            "use_sentiment": False,
        }

    return supervisor_node
