from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str

    # LLM provider: "openai" | "ollama"
    llm_provider: str = "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # PostgreSQL
    postgres_user: str = "finassist"
    postgres_password: str = "changeme"
    postgres_db: str = "finassist_db"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_dsn: str | None = None  # If set directly, overrides computed field

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # NewsAPI
    newsapi_key: str = ""

    # Agent tuning
    sentiment_lambda: float = 0.15
    monte_carlo_simulations: int = 5000
    monte_carlo_horizon_days: int = 252

    # LangSmith tracing
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "asistente-financiero"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_postgres_dsn(self) -> str:
        if self.postgres_dsn:
            return self.postgres_dsn
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
