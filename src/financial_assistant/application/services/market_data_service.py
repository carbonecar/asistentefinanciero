from financial_assistant.application.dtos.requests import FetchMarketDataCommand
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway
from financial_assistant.domain.ports.repositories import IMarketDataRepository


class MarketDataService:
    def __init__(
        self,
        gateway: IMarketDataGateway,
        repository: IMarketDataRepository,
    ) -> None:
        self._gateway = gateway
        self._repository = repository

    async def fetch_and_persist(self, cmd: FetchMarketDataCommand) -> dict[str, list[OHLCV]]:
        results: dict[str, list[OHLCV]] = {}
        for ticker in cmd.tickers:
            records = await self._gateway.fetch_ohlcv(ticker, period=cmd.period)
            if records:
                await self._repository.save_ohlcv(records)
            results[ticker] = records
        return results

    async def get_benchmark(self, benchmark: str = "SPY") -> list[OHLCV]:
        return await self._gateway.fetch_benchmark(benchmark)  # type: ignore[arg-type]
