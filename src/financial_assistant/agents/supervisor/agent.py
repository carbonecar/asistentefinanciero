import json
import logging
import re
import traceback
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage

from financial_assistant.agents.llm_factory import make_llm
from financial_assistant.agents.state import VALID_INTENTS, AgentState
from financial_assistant.agents.supervisor.prompts import CLASSIFY_INTENT_SCHEMA, FALLBACK_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_DEFAULT_RESULT: dict = {  # type: ignore[type-arg]
    "intents": ["general"],
    "active_tickers": [],
    "period": "1y",
    "use_sentiment": False,
    "positions": [],
}


def _build_result(args: dict) -> dict:  # type: ignore[type-arg]
    raw = args.get("intents", ["general"])
    intents = [i for i in raw if i in VALID_INTENTS] or ["general"]
    positions = args.get("positions") or []
    logger.info("[Supervisor] intents=%s tickers=%s positions=%s", intents, args.get("tickers", []), positions)
    return {
        "intents": intents,
        "active_tickers": [t.upper() for t in args.get("tickers", [])],
        "period": args.get("period", "1y"),
        "use_sentiment": args.get("use_sentiment", False),
        "positions": positions,
    }


def _parse_json_from_text(text: str) -> dict | None:  # type: ignore[type-arg]
    """Extract JSON object from LLM text response (fallback for models with weak tool calling)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return cast(dict[str, Any], json.loads(match.group()))
    except json.JSONDecodeError:
        return None


def make_supervisor_node(  # type: ignore[no-untyped-def]
    model: str,
    api_key: str = "",
    provider: str = "openai",
    base_url: str = "http://localhost:11434",
):
    llm = make_llm(provider=provider, model=model, temperature=0, api_key=api_key, base_url=base_url)
    llm_with_tools = llm.bind_tools([{"type": "function", "function": CLASSIFY_INTENT_SCHEMA}])

    async def supervisor_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        try:
            response = await llm_with_tools.ainvoke(messages)
            tool_calls = getattr(response, "tool_calls", [])
            if tool_calls:
                return _build_result(tool_calls[0]["args"])

            # Fallback: model didn't use tool calling (common with local models like llama3.1).
            # Re-prompt with a minimal JSON-only instruction.
            logger.warning("[Supervisor] No tool_calls in response — trying JSON fallback")
            user_text = state["messages"][-1].content if state["messages"] else ""
            fallback_messages = [
                SystemMessage(content=FALLBACK_PROMPT),
                HumanMessage(content=str(user_text)),
            ]
            fallback_response = await llm.ainvoke(fallback_messages)
            content = getattr(fallback_response, "content", "") or ""
            args = _parse_json_from_text(str(content))
            if args:
                return _build_result(args)

            logger.warning("[Supervisor] JSON fallback also failed, content=%r", content[:200])

        except Exception:
            logger.error("Supervisor LLM call failed — routing to 'general':\n%s", traceback.format_exc())

        return dict(_DEFAULT_RESULT)

    return supervisor_node
