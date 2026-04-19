"""
Dependency injection container.
Wires together all infrastructure adapters and application services.
"""

from financial_assistant.agents.graph import build_graph
from financial_assistant.agents.quant.monte_carlo import MonteCarloSimulator
from financial_assistant.agents.quant.optimizer import PortfolioOptimizer
from financial_assistant.application.services.audit_service import AuditService
from financial_assistant.application.services.market_data_service import MarketDataService
from financial_assistant.application.services.news_service import NewsService
from financial_assistant.application.services.portfolio_service import PortfolioService
from financial_assistant.application.services.quant_service import QuantService
from financial_assistant.config.settings import Settings
from financial_assistant.domain.models.analysis import OptimizedWeights
from financial_assistant.infrastructure.db.engine import build_engine, build_session_factory
from financial_assistant.infrastructure.db.repositories.market_data_repository import (
    PostgresMarketDataRepository,
)
from financial_assistant.infrastructure.db.repositories.portfolio_repository import (
    PostgresPortfolioRepository,
)
from financial_assistant.infrastructure.fx.dolarapi_gateway import DolarApiGateway
from financial_assistant.infrastructure.market.yfinance_gateway import YFinanceGateway
from financial_assistant.infrastructure.news.newsapi_gateway import NewsAPIGateway
from financial_assistant.infrastructure.nlp.sentiment_analyzer import TextBlobSentimentAnalyzer


class Container:
    def __init__(self, settings: Settings) -> None:  # pylint: disable=too-many-locals
        self.settings = settings

        # DB
        engine = build_engine(settings.effective_postgres_dsn, echo=settings.sql_echo)
        session_factory = build_session_factory(engine)

        # Repositories
        portfolio_repo = PostgresPortfolioRepository(session_factory)
        market_data_repo = PostgresMarketDataRepository(session_factory)

        # Gateways
        market_gateway = YFinanceGateway()
        news_gateway = NewsAPIGateway(api_key=settings.newsapi_key)

        # Application services
        self.portfolio_service = PortfolioService(portfolio_repo)
        market_data_service = MarketDataService(market_gateway, market_data_repo)
        audit_service = AuditService(portfolio_repo, market_gateway)

        optimizer = PortfolioOptimizer(sentiment_lambda=settings.sentiment_lambda)
        simulator = MonteCarloSimulator(
            n_simulations=settings.monte_carlo_simulations,
            horizon_days=settings.monte_carlo_horizon_days,
        )

        # Adapt optimizer/simulator to protocol interfaces
        class _OptimizerAdapter:
            def minimum_variance(self, ohlcv_by_ticker: dict, sentiment_map: dict) -> object:  # type: ignore[type-arg]
                return optimizer.minimum_variance(ohlcv_by_ticker, sentiment_map)

        class _SimulatorAdapter:
            def simulate(self, weights: object, ohlcv_by_ticker: dict, initial_value: float) -> object:  # type: ignore[type-arg]

                assert isinstance(weights, OptimizedWeights)
                return simulator.simulate(weights, ohlcv_by_ticker, initial_value)

        quant_service = QuantService(portfolio_repo, market_gateway, _OptimizerAdapter(), _SimulatorAdapter())
        news_service = NewsService(news_gateway, TextBlobSentimentAnalyzer())
        fx_gateway = DolarApiGateway()

        # LangGraph compiled graph
        llm_model = settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model
        self.graph = build_graph(
            audit_service=audit_service,
            market_data_service=market_data_service,
            quant_service=quant_service,
            news_service=news_service,
            fx_gateway=fx_gateway,
            llm_provider=settings.llm_provider,
            llm_model=llm_model,
            llm_api_key=settings.openai_api_key,
            llm_base_url=settings.ollama_base_url,
        )
