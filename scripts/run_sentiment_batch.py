"""
Batch script to pre-compute and persist historical news sentiment.

Usage:
    python -m scripts.run_sentiment_batch
    python -m scripts.run_sentiment_batch --lookback-days 400

Reads ANALYSIS_TICKERS from .env (comma-separated, e.g. "AAPL,TSLA,GGAL.BA").
Fetches N-day Finnhub news per ticker, runs FinBERT sentiment day-by-day,
and upserts the results into the sentiment_history DB table.

Requires:
    - FINNHUB_API_KEY in .env
    - ANALYSIS_TICKERS in .env
    - DB running and migration 0002 applied (make migrate)
"""

import argparse
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


async def main(lookback_days: int) -> None:
    settings = Settings()

    tickers = settings.analysis_tickers_list
    if not tickers:
        print("[batch] ERROR: ANALYSIS_TICKERS is empty. Set it in .env, e.g. ANALYSIS_TICKERS=AAPL,TSLA,GGAL.BA")
        sys.exit(1)

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

    total_saved = 0
    for ticker in tickers:
        print(f"[batch] [{ticker}] Fetching news and running FinBERT...")
        query = HistoricalNewsQuery(tickers=[ticker], lookback_days=lookback_days)
        results = await service.analyze_historical_sentiment(query)
        records = results.get(ticker, [])
        if records:
            await repo.save(records)
            total_saved += len(records)
            print(f"[batch] [{ticker}] Saved {len(records)} daily records.")
        else:
            print(f"[batch] [{ticker}] No records found.")

    print(f"[batch] Done. Total records saved: {total_saved}.")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch historical sentiment computation")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=60,
        help="Number of calendar days to look back from today (default: 60)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.lookback_days))
