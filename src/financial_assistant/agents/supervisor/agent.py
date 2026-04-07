import json
import logging

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from financial_assistant.agents.state import AgentState
from financial_assistant.agents.supervisor.prompts import CLASSIFY_INTENT_SCHEMA, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def make_supervisor_node(model: str, api_key: str):  # type: ignore[no-untyped-def]
    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    llm_with_tools = llm.bind_tools([{"type": "function", "function": CLASSIFY_INTENT_SCHEMA}])

    async def supervisor_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        try:
            response = await llm_with_tools.ainvoke(messages)
            tool_calls = getattr(response, "tool_calls", [])
            if tool_calls:
                args = tool_calls[0]["args"]
                return {
                    "intent": args.get("intent", "general"),
                    "active_tickers": [t.upper() for t in args.get("tickers", [])],
                    "period": args.get("period", "1y"),
                    "use_sentiment": args.get("use_sentiment", False),
                    "messages": [response],
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
