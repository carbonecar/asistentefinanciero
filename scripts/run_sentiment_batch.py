"""
Batch script to pre-compute and persist historical news sentiment.

Usage:
    python -m scripts.run_sentiment_batch

Reads ANALYSIS_TICKERS from .env (comma-separated, e.g. "AAPL,TSLA,GGAL.BA").
Fetches 60-day Finnhub news per ticker, runs FinBERT sentiment day-by-day,
and upserts the results into the sentiment_history DB table.

Requires:
    - FINNHUB_API_KEY in .env
    - ANALYSIS_TICKERS in .env
    - DB running and migration 0002 applied (make migrate)
"""

import asyncio
import sys
from datetime import date, timedelta

from financial_assistant.application.dtos.requests import HistoricalNewsQuery
from financial_assistant.config.settings import Settings
from financial_assistant.infrastructure.db.engine import build_engine, build_session_factory
from financial_assistant.infrastructure.db.repositories.sentiment_history_repository import (
    PostgresSentimentHistoryRepository,
)
from financial_assistant.infrastructure.news.finnhub_news_gateway import FinnhubNewsGateway
from financial_assistant.infrastructure.nlp.finbert_sentiment_analyzer import FinBERTSentimentAnalyzer


async def main() -> None:
    settings = Settings()

    tickers = settings.analysis_tickers_list
    if not tickers:
        print("[batch] ERROR: ANALYSIS_TICKERS is empty. Set it in .env, e.g. ANALYSIS_TICKERS=AAPL,TSLA,GGAL.BA")
        sys.exit(1)

    lookback_days = 60
    today = date.today()
    from_date = today - timedelta(days=lookback_days)

    print(f"[batch] Tickers: {tickers}")
    print(f"[batch] Range: {from_date} → {today}")

    # Build dependencies without the full Container to avoid spinning up LangGraph
    engine = build_engine(settings.effective_postgres_dsn, echo=False)
    session_factory = build_session_factory(engine)

    gateway = FinnhubNewsGateway(api_key=settings.finnhub_api_key)
    analyzer = FinBERTSentimentAnalyzer()
    repo = PostgresSentimentHistoryRepository(session_factory)

    # Import NewsService locally to avoid circular container wiring
    from financial_assistant.application.services.news_service import NewsService  # noqa: PLC0415

    service = NewsService(gateway, analyzer, repo)

    query = HistoricalNewsQuery(tickers=tickers, lookback_days=lookback_days)

    print("[batch] Fetching news and running FinBERT sentiment analysis...")
    results = await service.analyze_historical_sentiment(query)

    # Flatten and save to DB
    all_records = [day for daily in results.values() for day in daily]

    print(f"[batch] Computed {len(all_records)} daily records across {len(tickers)} ticker(s).")
    if all_records:
        await repo.save(all_records)
        print("[batch] Saved to sentiment_history table.")
    else:
        print("[batch] No records to save (no articles found for the requested period).")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
