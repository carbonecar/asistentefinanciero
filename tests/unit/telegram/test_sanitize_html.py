"""
Unit tests for _sanitize_for_html_mode().

Pipeline bajo test:
  1. _MARKDOWN_BOLD convierte **x** → <b>x</b>
  2. html.escape escapa TODO el texto (incluye los <b> del paso anterior)
  3. _SAFE_HTML_TAG restaura solo las etiquetas permitidas

Cubre:
- Conversión de markdown bold a <b> (foco principal de la corrección)
- Etiquetas HTML seguras que ya venían en el texto son restauradas
- Etiquetas HTML no permitidas (script, img, etc.) quedan escapadas
- Caracteres especiales HTML (&, <, >, ") quedan escapados
- Asterisco simple no se convierte (requiere **)
- Inyección HTML vía markdown queda neutralizada
"""

from financial_assistant.telegram.handlers.message_handler import _sanitize_for_html_mode

# ---------------------------------------------------------------------------
# Markdown bold → <b>
# ---------------------------------------------------------------------------


class TestMarkdownBoldConversion:
    def test_bold_word_converted(self):
        assert _sanitize_for_html_mode("**bold**") == "<b>bold</b>"

    def test_bold_in_sentence(self):
        result = _sanitize_for_html_mode("El retorno fue **positivo** este mes.")
        assert result == "El retorno fue <b>positivo</b> este mes."

    def test_multiple_bold_spans(self):
        result = _sanitize_for_html_mode("**Ticker**: AAPL | **Retorno**: 12.5%")
        assert result == "<b>Ticker</b>: AAPL | <b>Retorno</b>: 12.5%"

    def test_bold_with_spaces_inside(self):
        result = _sanitize_for_html_mode("**precio de referencia**")
        assert result == "<b>precio de referencia</b>"

    def test_single_asterisk_at_boundary_converted_to_bold(self):
        # *word* en límite de no-palabra → se convierte a <b>word</b>
        result = _sanitize_for_html_mode("*single*")
        assert result == "<b>single</b>"

    def test_single_asterisk_between_word_chars_not_converted(self):
        # 5*180 — asterisco entre caracteres alfanuméricos no se convierte
        assert _sanitize_for_html_mode("5*180") == "5*180"

    def test_single_asterisk_no_closing_not_converted(self):
        # Un solo * sin par de cierre no se convierte
        assert "*suelto" in _sanitize_for_html_mode("precio *suelto sin cierre")

    def test_triple_asterisk_converts_inner_bold(self):
        # ***triple*** → single-bold convierte *triple* (inner), luego double-bold
        # el resultado contiene <b>triple</b>
        result = _sanitize_for_html_mode("***triple***")
        assert "<b>triple</b>" in result

    def test_empty_string(self):
        assert _sanitize_for_html_mode("") == ""

    def test_no_markup_passthrough(self):
        text = "Texto sin formato especial."
        assert _sanitize_for_html_mode(text) == text


# ---------------------------------------------------------------------------
# Etiquetas HTML seguras restauradas
# ---------------------------------------------------------------------------


class TestSafeHtmlTagsPreserved:
    def test_b_tag_preserved(self):
        assert _sanitize_for_html_mode("<b>negrita</b>") == "<b>negrita</b>"

    def test_i_tag_preserved(self):
        assert _sanitize_for_html_mode("<i>itálica</i>") == "<i>itálica</i>"

    def test_u_tag_preserved(self):
        assert _sanitize_for_html_mode("<u>subrayado</u>") == "<u>subrayado</u>"

    def test_s_tag_preserved(self):
        assert _sanitize_for_html_mode("<s>tachado</s>") == "<s>tachado</s>"

    def test_code_tag_preserved(self):
        assert _sanitize_for_html_mode("<code>ticker</code>") == "<code>ticker</code>"

    def test_closing_b_tag_preserved(self):
        assert _sanitize_for_html_mode("<b>texto</b>") == "<b>texto</b>"

    def test_safe_tag_mixed_with_text(self):
        result = _sanitize_for_html_mode("Retorno: <b>+12%</b> anual.")
        assert result == "Retorno: <b>+12%</b> anual."


# ---------------------------------------------------------------------------
# Etiquetas no permitidas quedan escapadas
# ---------------------------------------------------------------------------


class TestUnsafeTagsEscaped:
    def test_script_tag_escaped(self):
        result = _sanitize_for_html_mode("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_img_tag_escaped(self):
        result = _sanitize_for_html_mode('<img src="x" onerror="alert(1)">')
        assert "<img" not in result

    def test_a_tag_escaped(self):
        result = _sanitize_for_html_mode('<a href="evil.com">click</a>')
        assert "<a " not in result

    def test_div_tag_escaped(self):
        result = _sanitize_for_html_mode("<div>contenido</div>")
        assert "<div>" not in result
        assert "&lt;div&gt;" in result


# ---------------------------------------------------------------------------
# Caracteres especiales HTML escapados
# ---------------------------------------------------------------------------


class TestHtmlSpecialCharsEscaped:
    def test_ampersand_escaped(self):
        assert _sanitize_for_html_mode("S&P 500") == "S&amp;P 500"

    def test_less_than_escaped(self):
        result = _sanitize_for_html_mode("precio < 100")
        assert "&lt;" in result
        assert "<" not in result.replace("<b>", "").replace("</b>", "")

    def test_greater_than_escaped(self):
        result = _sanitize_for_html_mode("precio > 100")
        assert "&gt;" in result

    def test_double_quote_escaped(self):
        result = _sanitize_for_html_mode('ticker "AAPL"')
        assert "&quot;" in result or '"' not in result


# ---------------------------------------------------------------------------
# Inyección HTML vía markdown — contenido interno queda escapado
# ---------------------------------------------------------------------------


class TestMarkdownInjectionSafe:
    def test_script_inside_bold_is_neutralized(self):
        result = _sanitize_for_html_mode("**<script>alert(1)</script>**")
        # La etiqueta b se restaura, pero script queda escapado dentro
        assert "<b>" in result
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_img_inside_bold_is_neutralized(self):
        result = _sanitize_for_html_mode('**<img src=x onerror=alert(1)>**')
        assert "<b>" in result
        assert "<img" not in result
