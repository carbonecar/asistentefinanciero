from abc import ABC, abstractmethod

from financial_assistant.domain.models.fx import ExchangeRate


class IExchangeRateGateway(ABC):
    @abstractmethod
    async def fetch_rates(self) -> list[ExchangeRate]:
        """Fetch current ARS/USD exchange rates (oficial, blue, MEP, mayorista)."""
        ...
