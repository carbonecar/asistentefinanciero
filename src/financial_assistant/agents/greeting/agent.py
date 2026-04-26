import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from financial_assistant.agents.greeting.prompts import GREETING_SYSTEM_PROMPT, GREETING_USER_TEMPLATE
from financial_assistant.agents.llm_factory import make_llm
from financial_assistant.agents.state import AgentState

logger = logging.getLogger(__name__)

from typing import Callable, Awaitable, Dict, Any

def make_greeting_node(
    model: str,
    api_key: str = "", 
    provider: str = "openai", 
    base_url: str = "http://localhost:11434"
) -> Callable[[AgentState], Awaitable[Dict[str, Any]]]:
    llm = make_llm(provider=provider, model=model, temperature=0, api_key=api_key, base_url=base_url)

    async def greeting_node(state: AgentState) -> Dict[str, Any]:
        logger.info("[GREETING] user=%s", state.get("user_id"))
        user_message = state.get("user_message", "")
        prompt = GREETING_USER_TEMPLATE.format(user_message=user_message)
        messages = [SystemMessage(content=GREETING_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        try:
            response = await llm.ainvoke(messages)
            return {
                "final_response": response.content,
                "messages": [AIMessage(content=response.content)],
                "errors": [],
            }
        except Exception as exc:
            logger.error("Greeting agent LLM call failed: %s", exc)
            return {
                "final_response": "¡Hola! ¿En qué puedo ayudarte hoy?",
                "errors": [str(exc)],
            }
    return greeting_node
