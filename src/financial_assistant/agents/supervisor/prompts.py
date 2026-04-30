import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent

SYSTEM_PROMPT = (_DIR / "system_prompt.md").read_text(encoding="utf-8")
FALLBACK_PROMPT = (_DIR / "fallback_prompt.md").read_text(encoding="utf-8")
CLASSIFY_INTENT_SCHEMA: dict[str, Any] = json.loads((_DIR / "classify_intent_schema.json").read_text(encoding="utf-8"))
