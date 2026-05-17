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
from financial_assistant.application.services.quant_service import OptimizerProtocol, QuantService, SimulatorProtocol
from financial_assistant.config.settings import Settings
from financial_assistant.domain.models.analysis import OptimizedWeights, SimulationResult
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.infrastructure.db.engine import build_engine, build_session_factory
from financial_assistant.infrastructure.db.repositories.market_data_repository import (
    PostgresMarketDataRepository,
)
from financial_assistant.infrastructure.db.repositories.portfolio_repository import (
    PostgresPortfolioRepository,
)
from financial_assistant.infrastructure.fx.dolarapi_gateway import DolarApiGateway
from financial_assistant.infrastructure.market.yfinance_gateway import YFinanceGateway
from financial_assistant.infrastructure.news.finnhub_news_gateway import FinnhubNewsGateway
from financial_assistant.infrastructure.nlp.finbert_sentiment_analyzer import FinBERTSentimentAnalyzer


class Container:
    """
    Contenedor de inyección de dependencias del sistema.

    Responsable de instanciar y cablear todos los componentes de la aplicación
    en el orden correcto, respetando la regla de dependencias de la arquitectura
    hexagonal: las capas internas (dominio, aplicación) no conocen las externas
    (infraestructura, agentes).

    Es el único lugar del sistema donde se resuelven las implementaciones
    concretas de cada interfaz (puerto → adaptador).

    Atributos públicos:
        settings: Configuración de la aplicación.
        portfolio_service: Servicio de gestión de posiciones, expuesto para
            uso directo desde handlers de Telegram si fuera necesario.
        graph: Grafo LangGraph compilado, listo para ser invocado con .ainvoke().
    """

    def __init__(self, settings: Settings) -> None:  # pylint: disable=too-many-locals
        """
        Inicializa el contenedor instanciando y cableando todos los componentes.

        El orden de instanciación es importante:
        1. Base de datos (engine + session factory)
        2. Repositorios (dependen de la DB)
        3. Gateways externos (yfinance, newsapi, dolarapi)
        4. Servicios de aplicación (dependen de repositorios y gateways)
        5. Adaptadores de optimizador y simulador
        6. Grafo LangGraph (depende de todos los servicios)

        Args:
            settings: Configuración cargada desde variables de entorno (.env).
        """
        self.settings = settings

        # DB
        engine = build_engine(settings.effective_postgres_dsn, echo=settings.sql_echo)
        session_factory = build_session_factory(engine)

        # Repositorios
        portfolio_repo = PostgresPortfolioRepository(session_factory)
        market_data_repo = PostgresMarketDataRepository(session_factory)

        # Gateways externos
        market_gateway = YFinanceGateway()
        news_gateway = FinnhubNewsGateway(api_key=settings.finnhub_api_key)

        # Servicios de aplicación
        self.portfolio_service = PortfolioService(portfolio_repo)
        market_data_service = MarketDataService(market_gateway, market_data_repo)
        audit_service = AuditService(portfolio_repo, market_gateway, market_data_repo)

        optimizer = PortfolioOptimizer(sentiment_lambda=settings.sentiment_lambda)
        simulator = MonteCarloSimulator(
            n_simulations=settings.monte_carlo_simulations,
            horizon_days=settings.monte_carlo_horizon_days,
        )

        # Adaptadores internos que ajustan la firma de optimizer y simulator
        # a los protocolos esperados por QuantService
        class _OptimizerAdapter(OptimizerProtocol):
            """Adapta PortfolioOptimizer al protocolo OptimizerProtocol de QuantService."""

            def minimum_variance(
                self, ohlcv_by_ticker: dict[str, list[OHLCV]], sentiment_map: dict[str, float]
            ) -> OptimizedWeights | None:
                return optimizer.minimum_variance(ohlcv_by_ticker, sentiment_map)

        class _SimulatorAdapter(SimulatorProtocol):
            """Adapta MonteCarloSimulator al protocolo SimulatorProtocol de QuantService."""

            def simulate(
                self, weights: OptimizedWeights | None, ohlcv_by_ticker: dict[str, list[OHLCV]], initial_value: float
            ) -> SimulationResult | None:
                if weights is None:
                    return None
                return simulator.simulate(weights, ohlcv_by_ticker, initial_value)

        quant_service = QuantService(portfolio_repo, market_gateway, _OptimizerAdapter(), _SimulatorAdapter())
        news_service = NewsService(news_gateway, FinBERTSentimentAnalyzer())
        fx_gateway = DolarApiGateway()

        # Grafo LangGraph compilado
        # Selecciona el modelo según el proveedor configurado
        llm_model = settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model
        self.graph = build_graph(
            audit_service=audit_service,
            market_data_service=market_data_service,
            portfolio_service=self.portfolio_service,
            quant_service=quant_service,
            news_service=news_service,
            fx_gateway=fx_gateway,
            llm_provider=settings.llm_provider,
            llm_model=llm_model,
            llm_api_key=settings.openai_api_key,
            llm_base_url=settings.ollama_base_url,
        )
