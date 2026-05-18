"""
Tests para objetivos C y D del hotfix:

Objetivo C — asteriscos simples en respuestas:
- UNSUPPORTED_RESPONSE no usa *Auditar* ni variantes con asterisco simple.
- El sanitizador convierte *Auditar*, *Optimizar*, *Noticias*, *Agregar posiciones*
  a su equivalente HTML seguro.

Objetivo D — lenguaje prohibido:
- SYNTHESIS_SYSTEM_PROMPT contiene explícitamente como prohibidas las frases
  "proceder con la compra", "confirmar la compra", etc.
- SYNTHESIS_USER_TEMPLATE no instruye a "ofrecer el siguiente paso lógico"
  de forma que induzca al LLM a ofrecer ARS sin que se lo pidan.
"""

from financial_assistant.agents.graph import UNSUPPORTED_RESPONSE
from financial_assistant.agents.ux_agent.prompts import (
    SYNTHESIS_SYSTEM_PROMPT,
    SYNTHESIS_USER_TEMPLATE,
)
from financial_assistant.telegram.handlers.message_handler import _sanitize_for_html_mode

# ---------------------------------------------------------------------------
# Objetivo C — UNSUPPORTED_RESPONSE no usa asterisco simple como énfasis
# ---------------------------------------------------------------------------


class TestUnsupportedResponseNoAsterisks:
    def test_no_asterisk_auditar(self):
        assert "*Auditar*" not in UNSUPPORTED_RESPONSE

    def test_no_asterisk_optimizar(self):
        assert "*Optimizar*" not in UNSUPPORTED_RESPONSE

    def test_no_asterisk_noticias(self):
        assert "*Noticias*" not in UNSUPPORTED_RESPONSE

    def test_no_asterisk_agregar_posiciones(self):
        assert "*Agregar posiciones*" not in UNSUPPORTED_RESPONSE

    def test_uses_html_bold_auditar(self):
        assert "<b>Auditar</b>" in UNSUPPORTED_RESPONSE

    def test_uses_html_bold_optimizar(self):
        assert "<b>Optimizar</b>" in UNSUPPORTED_RESPONSE

    def test_uses_html_bold_noticias(self):
        assert "<b>Noticias</b>" in UNSUPPORTED_RESPONSE

    def test_uses_html_bold_agregar_posiciones(self):
        assert "<b>Agregar posiciones</b>" in UNSUPPORTED_RESPONSE


# ---------------------------------------------------------------------------
# Objetivo C — sanitizador convierte *texto* a <b>texto</b>
# (para respuestas LLM que usen asterisco simple a pesar del prompt)
# ---------------------------------------------------------------------------


class TestSanitizerConvertsAsterisks:
    def test_asterisk_auditar(self):
        result = _sanitize_for_html_mode("• *Auditar* tu cartera")
        assert "*Auditar*" not in result
        assert "<b>Auditar</b>" in result

    def test_asterisk_optimizar(self):
        result = _sanitize_for_html_mode("• *Optimizar* tu portfolio")
        assert "<b>Optimizar</b>" in result

    def test_asterisk_noticias(self):
        result = _sanitize_for_html_mode("• *Noticias* y sentimiento")
        assert "<b>Noticias</b>" in result

    def test_asterisk_agregar_posiciones(self):
        result = _sanitize_for_html_mode("• *Agregar posiciones* a tu cartera")
        assert "<b>Agregar posiciones</b>" in result

    def test_asterisk_agregar_posicion_singular(self):
        result = _sanitize_for_html_mode("*Agregar posición*")
        assert "<b>Agregar posición</b>" in result


# ---------------------------------------------------------------------------
# Objetivo D — SYNTHESIS_SYSTEM_PROMPT prohíbe el lenguaje incorrecto
# ---------------------------------------------------------------------------


class TestPromptProhibitsLanguage:
    def test_prohibits_proceder_con_la_compra(self):
        assert "proceder con la compra" in SYNTHESIS_SYSTEM_PROMPT

    def test_prohibits_confirmar_la_compra(self):
        assert "confirmar la compra" in SYNTHESIS_SYSTEM_PROMPT

    def test_prohibits_acciones_a_comprar(self):
        assert "acciones a comprar" in SYNTHESIS_SYSTEM_PROMPT

    def test_prohibits_seguir_adelante_con_la_compra(self):
        assert "seguir adelante con la compra" in SYNTHESIS_SYSTEM_PROMPT

    def test_prohibits_realizar_la_compra(self):
        assert "realizar la compra" in SYNTHESIS_SYSTEM_PROMPT

    def test_prohibits_proceder_standalone(self):
        assert '"proceder"' in SYNTHESIS_SYSTEM_PROMPT

    def test_prohibits_ars_offer(self):
        assert "si querés calcular el equivalente en ARS" in SYNTHESIS_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Objetivo D — SYNTHESIS_USER_TEMPLATE no induce a ofrecer ARS como paso
# ---------------------------------------------------------------------------


class TestTemplateNoNextStepInduction:
    def test_no_siguiente_paso_logico(self):
        assert "siguiente paso lógico" not in SYNTHESIS_USER_TEMPLATE

    def test_principle_5_no_ars_induction(self):
        assert "no ofrezcas" in SYNTHESIS_USER_TEMPLATE

    def test_principle_3_no_proceder(self):
        assert "antes de proceder" not in SYNTHESIS_USER_TEMPLATE
