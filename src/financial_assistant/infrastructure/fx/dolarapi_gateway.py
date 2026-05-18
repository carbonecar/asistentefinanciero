"""
Adapter for dolarapi.com — free, no API key required.
Endpoint: GET https://dolarapi.com/v1/dolares
Returns rates for: oficial, blue, mep, mayorista, cripto, tarjeta.

Includes a 5-minute in-memory TTL cache to avoid hammering the API
on every agent invocation.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx

from financial_assistant.domain.models.fx import ExchangeRate
from financial_assistant.domain.ports.fx_gateway import IExchangeRateGateway

logger = logging.getLogger(__name__)

_DOLARAPI_URL = "https://dolarapi.com/v1/dolares"
# dolarapi.com returns MEP as casa="bolsa" (Dólar Bolsa / MEP). Include it and normalise below.
_CASAS_INTERES = {"oficial", "blue", "mep", "bolsa", "mayorista"}
_CASA_NORMALISE = {"bolsa": "mep"}  # API name → canonical name
_NOMBRE_NORMALISE = {"bolsa": "Dólar MEP"}
_CACHE_TTL = timedelta(minutes=5)


class DolarApiGateway(IExchangeRateGateway):
    def __init__(self) -> None:
        self._cache: list[ExchangeRate] = []
        self._cache_expires_at: datetime = datetime.min

    async def fetch_rates(self) -> list[ExchangeRate]:
        if datetime.now() < self._cache_expires_at and self._cache:
            logger.debug("FX rates served from cache (expires %s)", self._cache_expires_at)
            return self._cache

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(_DOLARAPI_URL)
                response.raise_for_status()
                data = response.json()

            rates = [self._parse(item) for item in data if item.get("casa") in _CASAS_INTERES]
            self._cache = rates
            self._cache_expires_at = datetime.now() + _CACHE_TTL
            logger.info("FX rates refreshed: %s", [r.casa for r in rates])
            return rates

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("DolarApi fetch failed: %s — returning cached/empty rates", exc)
            return self._cache  # return stale cache on error rather than crashing

    @staticmethod
    def _parse(item: dict) -> ExchangeRate:  # type: ignore[type-arg]
        updated_raw = item.get("fechaActualizacion", "")
        try:
            updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            updated_at = datetime.now()

        raw_casa = item["casa"]
        casa = _CASA_NORMALISE.get(raw_casa, raw_casa)
        nombre = _NOMBRE_NORMALISE.get(raw_casa) or item.get("nombre", raw_casa.capitalize())
        return ExchangeRate(
            casa=casa,
            nombre=nombre,
            compra=Decimal(str(item.get("compra") or 0)),
            venta=Decimal(str(item.get("venta") or 0)),
            updated_at=updated_at,
        )
