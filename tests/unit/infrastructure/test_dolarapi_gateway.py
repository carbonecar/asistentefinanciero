"""
Unit tests for DolarApiGateway._parse — verifies bolsa→mep normalization.

No network calls. All tests invoke _parse directly with synthetic API payloads.
"""

from decimal import Decimal

from financial_assistant.infrastructure.fx.dolarapi_gateway import DolarApiGateway


def _raw(casa: str, nombre: str, compra: float = 900.0, venta: float = 920.0) -> dict:
    return {
        "casa": casa,
        "nombre": nombre,
        "compra": compra,
        "venta": venta,
        "fechaActualizacion": "2026-05-18T10:00:00Z",
    }


class TestDolarApiParse:
    def test_bolsa_mapped_to_mep_casa(self):
        rate = DolarApiGateway._parse(_raw("bolsa", "Dólar Bolsa"))
        assert rate.casa == "mep"

    def test_bolsa_nombre_overridden_to_dolar_mep(self):
        rate = DolarApiGateway._parse(_raw("bolsa", "Dólar Bolsa"))
        assert rate.nombre == "Dólar MEP"

    def test_oficial_casa_unchanged(self):
        rate = DolarApiGateway._parse(_raw("oficial", "Dólar Oficial"))
        assert rate.casa == "oficial"
        assert rate.nombre == "Dólar Oficial"

    def test_blue_casa_unchanged(self):
        rate = DolarApiGateway._parse(_raw("blue", "Dólar Blue"))
        assert rate.casa == "blue"
        assert rate.nombre == "Dólar Blue"

    def test_mayorista_casa_unchanged(self):
        rate = DolarApiGateway._parse(_raw("mayorista", "Dólar Mayorista"))
        assert rate.casa == "mayorista"

    def test_compra_venta_preserved(self):
        rate = DolarApiGateway._parse(_raw("bolsa", "Dólar Bolsa", compra=1200.0, venta=1250.0))
        assert rate.compra == Decimal("1200.0")
        assert rate.venta == Decimal("1250.0")

    def test_invalid_date_falls_back_gracefully(self):
        item = {**_raw("bolsa", "Dólar Bolsa"), "fechaActualizacion": "not-a-date"}
        rate = DolarApiGateway._parse(item)
        assert rate is not None
        assert rate.casa == "mep"


class TestDolarApiFilterIncludes:
    def test_casas_interes_includes_bolsa(self):
        from financial_assistant.infrastructure.fx.dolarapi_gateway import _CASAS_INTERES

        assert "bolsa" in _CASAS_INTERES, "bolsa must be in _CASAS_INTERES so MEP is not filtered out"

    def test_casas_interes_includes_mep(self):
        from financial_assistant.infrastructure.fx.dolarapi_gateway import _CASAS_INTERES

        assert "mep" in _CASAS_INTERES

    def test_casas_interes_includes_core_types(self):
        from financial_assistant.infrastructure.fx.dolarapi_gateway import _CASAS_INTERES

        for expected in ("oficial", "blue", "mayorista"):
            assert expected in _CASAS_INTERES
