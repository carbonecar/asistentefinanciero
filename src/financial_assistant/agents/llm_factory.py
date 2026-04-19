"""
Factory para crear instancias de LLM según el proveedor configurado.
Soporta: openai | ollama
"""

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr


def make_llm(
    provider: str,
    model: str,
    temperature: float = 0.0,
    api_key: str = "",
    base_url: str = "http://localhost:11434",
) -> BaseChatModel:
    """
    Devuelve un ChatModel compatible con LangChain según el proveedor.

    - provider="openai": usa ChatOpenAI (requiere api_key)
    - provider="ollama": usa ChatOllama (requiere Ollama corriendo en base_url)

    Ambos exponen la misma interfaz: .ainvoke(), .bind_tools(), etc.
    Nota: para Ollama, usar modelos con soporte de tool calling:
          llama3.1, mistral-nemo, qwen2.5, etc.
    """
    if provider == "ollama":
        from langchain_ollama import ChatOllama  # pylint: disable=import-outside-toplevel

        return ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature,
        )

    # Default: openai
    from langchain_openai import ChatOpenAI  # pylint: disable=import-outside-toplevel

    return ChatOpenAI(
        model=model,
        api_key=SecretStr(api_key) if api_key else None,
        temperature=temperature,
    )
