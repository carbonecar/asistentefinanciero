import json
from datetime import date
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent

_SYSTEM_PROMPT_TEMPLATE = (_DIR / "system_prompt.md").read_text(encoding="utf-8")
FALLBACK_PROMPT = (_DIR / "fallback_prompt.md").read_text(encoding="utf-8")
CLASSIFY_INTENT_SCHEMA: dict[str, Any] = json.loads((_DIR / "classify_intent_schema.json").read_text(encoding="utf-8"))


def get_system_prompt() -> str:
    """Renderiza el system prompt inyectando la fecha actual.

    Se llama en cada invocación del supervisor para que la fecha de hoy
    quede siempre actualizada (importante en procesos long-running).

    Usa replace() en vez de format() porque el prompt contiene muchísimas
    llaves no escapadas en los ejemplos JSON-like (ej. {ticker:"AAPL"}),
    y format() las interpretaría como placeholders.
    """
    return _SYSTEM_PROMPT_TEMPLATE.replace("{today}", date.today().isoformat())
