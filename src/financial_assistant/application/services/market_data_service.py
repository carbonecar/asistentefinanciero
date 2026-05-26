import logging
from datetime import date
from typing import Literal

from financial_assistant.application.dtos.requests import FetchMarketDataCommand
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway
from financial_assistant.domain.ports.repositories import IMarketDataRepository

logger = logging.getLogger(__name__)


class MarketDataService:
    def __init__(
        self,
        gateway: IMarketDataGateway,
        repository: IMarketDataRepository,
    ) -> None:
        self._gateway = gateway
        self._repository = repository

    async def fetch_and_persist(self, cmd: FetchMarketDataCommand) -> dict[str, list[OHLCV]]:
        """
        Para cada ticker en cmd.tickers, intenta obtener los datos de OHLCV desde el gateway.
        Si se obtienen datos, los guarda en el repositorio.
        Devuelve un diccionario con los tickers y sus respectivos listas de OHLCV.
        """
        results: dict[str, list[OHLCV]] = {}
        for ticker in cmd.tickers:
            records = await self._gateway.fetch_ohlcv(ticker, period=cmd.period)
            if records:
                await self._repository.save_ohlcv(records)
            results[ticker] = records
        return results

    async def get_price_at_date(self, ticker: str, target_date: date) -> float | None:
        from datetime import timedelta

        logger.info("[MarketDataService] get_price_at_date ticker=%s target_date=%s", ticker, target_date)

        # Buscar en DB con ventana de ±5 días (cubre fines de semana y feriados)
        records = await self._repository.get_ohlcv(
            ticker,
            target_date - timedelta(days=5),
            target_date + timedelta(days=5),
        )

        logger.info("[MarketDataService] get_price_at_date found %d records in DB", len(records))

        if not records:
            # No está en DB — descargar desde el gateway con rango suficiente
            # para cubrir target_date (máximo 10 años hacia atrás)
            records = await self._gateway.fetch_ohlcv(ticker, period="max")
            if not records:
                return None
            # Filtrar solo registros cercanos a target_date
            records = [r for r in records if abs((r.date - target_date).days) <= 5]

        if not records:
            logger.warning(
                "[MarketDataService] get_price_at_date no records found for ticker=%s target_date=%s",
                ticker,
                target_date,
            )
            return None

        # Retornar el registro más cercano a target_date
        closest = min(records, key=lambda r: abs((r.date - target_date).days))
        return float(closest.close)

    async def get_benchmark(self, benchmark: Literal["SPY", "^GSPC", "GC=F"] = "SPY") -> list[OHLCV]:
        """
        Obtiene los datos de OHLCV para un benchmark específico.
         - Primero intenta obtener los datos de la base de datos.
         - Si no encuentra datos, intenta obtenerlos del gateway.
         - Retorna la lista de OHLCV obtenida, o una lista vacía si no se encuentran datos.
        """
        benchmark_list: list[OHLCV] = await self._gateway.fetch_benchmark(benchmark)
        return benchmark_list
