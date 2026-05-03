"""
Unit tests for _GREETING_RE — greeting detection pattern in message_handler.

Cubre:
- Palabras de saludo reconocidas (hola, hi, inicio, buenas, hey, menú, menu, comenzar, start)
- Variantes con puntuación (!, ?, .)
- Variantes con mayúsculas
- Espacios antes/después del texto
- Mensajes que NO son saludos (no deben activar el menú)
"""


from financial_assistant.telegram.handlers.message_handler import _GREETING_RE


class TestGreetingRecognized:
    def test_hola(self):
        assert _GREETING_RE.match("hola")

    def test_hi(self):
        assert _GREETING_RE.match("hi")

    def test_inicio(self):
        assert _GREETING_RE.match("inicio")

    def test_buenas(self):
        assert _GREETING_RE.match("buenas")

    def test_hey(self):
        assert _GREETING_RE.match("hey")

    def test_menu_sin_acento(self):
        assert _GREETING_RE.match("menu")

    def test_menu_con_acento(self):
        assert _GREETING_RE.match("menú")

    def test_comenzar(self):
        assert _GREETING_RE.match("comenzar")

    def test_start(self):
        assert _GREETING_RE.match("start")


class TestGreetingCaseInsensitive:
    def test_uppercase_hola(self):
        assert _GREETING_RE.match("HOLA")

    def test_mixed_case_hola(self):
        assert _GREETING_RE.match("Hola")

    def test_uppercase_inicio(self):
        assert _GREETING_RE.match("INICIO")


class TestGreetingWithPunctuation:
    def test_hola_exclamation(self):
        assert _GREETING_RE.match("hola!")

    def test_hola_question(self):
        assert _GREETING_RE.match("hola?")

    def test_hola_period(self):
        assert _GREETING_RE.match("hola.")

    def test_hola_multiple_exclamation(self):
        assert _GREETING_RE.match("hola!!")


class TestGreetingWithSpaces:
    def test_leading_space(self):
        assert _GREETING_RE.match(" hola")

    def test_trailing_space(self):
        assert _GREETING_RE.match("hola ")

    def test_both_spaces(self):
        assert _GREETING_RE.match("  hola  ")


class TestNonGreetingNotMatched:
    def test_financial_question(self):
        assert not _GREETING_RE.match("Cómo va mi cartera?")

    def test_register_position(self):
        assert not _GREETING_RE.match("Registrá 10 AAPL a 180 dólares")

    def test_audit_request(self):
        assert not _GREETING_RE.match("Auditá mi cartera")

    def test_empty_string(self):
        assert not _GREETING_RE.match("")

    def test_hola_with_more_text(self):
        assert not _GREETING_RE.match("hola como estás")

    def test_si(self):
        assert not _GREETING_RE.match("sí")

    def test_ok(self):
        assert not _GREETING_RE.match("ok")

    def test_news_request(self):
        assert not _GREETING_RE.match("Noticias de AAPL")
