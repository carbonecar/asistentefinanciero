"""
Unit tests verifying that data_fetcher only confirms positions that were
actually persisted to the repository, and propagates save errors to state.

All tests use AsyncMock — no DB or network required.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from financial_assistant.agents.data_fetcher.agent import make_data_fetcher_node
from financial_assistant.domain.models.portfolio import AssetType, Portfolio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _market_service() -> MagicMock:
    from datetime import date

    from financial_assistant.domain.models.market_data import OHLCV

    record = OHLCV(
        ticker="AAPL",
        date=date(2024, 1, 2),
        open=Decimal("150"),
        high=Decimal("155"),
        low=Decimal("148"),
        close=Decimal("152"),
        volume=1000,
    )
    svc = MagicMock()
    svc.fetch_and_persist = AsyncMock(return_value={"AAPL": [record]})
    return svc


def _portfolio_service_ok() -> MagicMock:
    svc = MagicMock()
    svc.add_position = AsyncMock()
    svc.get_or_create = AsyncMock(return_value=Portfolio(user_id=42, positions=[]))
    svc.remove_position = AsyncMock()
    return svc


def _portfolio_service_failing() -> MagicMock:
    svc = MagicMock()
    svc.add_position = AsyncMock(side_effect=RuntimeError("DB constraint violation"))
    svc.get_or_create = AsyncMock(return_value=Portfolio(user_id=42, positions=[]))
    svc.remove_position = AsyncMock()
    return svc


def _state(**kwargs) -> dict:
    base = {
        "user_id": 42,
        "user_message": "",
        "messages": [],
        "intents": ["data_fetch"],
        "active_tickers": ["AAPL"],
        "period": "1y",
        "use_sentiment": False,
        "positions": [],
        "market_data_result": None,
        "audit_report": None,
        "quant_result": None,
        "news_results": None,
        "exchange_rates": None,
        "final_response": None,
        "errors": [],
    }
    base.update(kwargs)
    return base


def _buy_pos(ticker: str = "AAPL", quantity: float = 10.0, avg_cost_usd: float = 150.0) -> dict:
    return {
        "ticker": ticker,
        "quantity": quantity,
        "avg_cost_usd": avg_cost_usd,
        "asset_type": "stock",
        "action": "buy",
    }


# ---------------------------------------------------------------------------
# P0 — confirmed positions reflect actual DB saves
# ---------------------------------------------------------------------------


class TestPositionPersistence:
    @pytest.mark.asyncio
    async def test_successful_save_returns_position_in_confirmed(self):
        ps = _portfolio_service_ok()
        node = make_data_fetcher_node(_market_service(), ps)

        result = await node(_state(positions=[_buy_pos("AAPL", 10.0, 150.0)]))

        confirmed = result["positions"]
        assert len(confirmed) == 1
        assert confirmed[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_register_position_does_not_confirm_when_repository_fails(self):
        ps = _portfolio_service_failing()
        node = make_data_fetcher_node(_market_service(), ps)

        result = await node(_state(positions=[_buy_pos("AAPL", 10.0, 150.0)]))

        assert result["positions"] == [], "failed save must not appear in confirmed positions"

    @pytest.mark.asyncio
    async def test_save_error_propagated_to_state_errors(self):
        ps = _portfolio_service_failing()
        node = make_data_fetcher_node(_market_service(), ps)

        result = await node(_state(positions=[_buy_pos("AAPL", 10.0, 150.0)]))

        assert result["errors"], "save error must be propagated to state errors"
        assert any("AAPL" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_partial_failure_only_confirms_saved_positions(self):
        call_count = 0

        async def add_position_sometimes_fails(cmd):
            nonlocal call_count
            call_count += 1
            if cmd.ticker == "MSFT":
                raise RuntimeError("MSFT write failed")

        ps = MagicMock()
        ps.add_position = AsyncMock(side_effect=add_position_sometimes_fails)
        ps.get_or_create = AsyncMock(return_value=Portfolio(user_id=42, positions=[]))
        ps.remove_position = AsyncMock()

        from datetime import date

        from financial_assistant.domain.models.market_data import OHLCV

        d = date(2024, 1, 2)
        records = {
            "AAPL": [OHLCV("AAPL", d, Decimal("150"), Decimal("155"), Decimal("148"), Decimal("152"), 1000)],
            "MSFT": [OHLCV("MSFT", d, Decimal("300"), Decimal("310"), Decimal("295"), Decimal("305"), 500)],
        }
        mkt = MagicMock()
        mkt.fetch_and_persist = AsyncMock(return_value=records)

        node = make_data_fetcher_node(mkt, ps)
        result = await node(
            _state(
                active_tickers=["AAPL", "MSFT"],
                positions=[
                    _buy_pos("AAPL", 10.0, 150.0),
                    _buy_pos("MSFT", 5.0, 300.0),
                ],
            )
        )

        confirmed_tickers = {p["ticker"] for p in result["positions"]}
        assert "AAPL" in confirmed_tickers
        assert "MSFT" not in confirmed_tickers
        assert any("MSFT" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_no_positions_returns_empty_confirmed(self):
        ps = _portfolio_service_ok()
        node = make_data_fetcher_node(_market_service(), ps)

        result = await node(_state(positions=[]))

        assert result["positions"] == []
        ps.add_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_buy_without_price_not_confirmed(self):
        ps = _portfolio_service_ok()
        node = make_data_fetcher_node(_market_service(), ps)

        no_price_pos = _buy_pos("AAPL", 10.0, 0.0)
        result = await node(_state(positions=[no_price_pos]))

        assert result["positions"] == []
        ps.add_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_asset_type_defaults_to_stock(self):
        ps = _portfolio_service_ok()
        node = make_data_fetcher_node(_market_service(), ps)

        pos = {**_buy_pos("AAPL", 10.0, 150.0), "asset_type": "UNKNOWN_TYPE"}
        result = await node(_state(positions=[pos]))

        assert len(result["positions"]) == 1
        cmd = ps.add_position.call_args[0][0]
        assert cmd.asset_type == AssetType.STOCK


# ---------------------------------------------------------------------------
# P0 — same user_id between data_fetcher and auditor
# ---------------------------------------------------------------------------


class TestUserIdConsistency:
    @pytest.mark.asyncio
    async def test_data_fetcher_uses_state_user_id(self):
        ps = _portfolio_service_ok()
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(user_id=999, positions=[_buy_pos("AAPL", 10.0, 150.0)]))

        cmd = ps.add_position.call_args[0][0]
        assert cmd.user_id == 999

    @pytest.mark.asyncio
    async def test_data_fetcher_and_auditor_use_same_user_id(self):
        from financial_assistant.agents.auditor.agent import make_auditor_node
        from financial_assistant.domain.models.analysis import AuditReport

        ps = _portfolio_service_ok()
        df_node = make_data_fetcher_node(_market_service(), ps)

        audit_service = MagicMock()
        audit_report = AuditReport(
            user_id=77,
            period_label="1y",
            portfolio_return=Decimal("0.10"),
            comparisons=[],
            top_performer="",
            worst_performer="",
            positions=[],
        )
        audit_service.audit = AsyncMock(return_value=audit_report)
        auditor_node = make_auditor_node(audit_service)

        state = _state(user_id=77, positions=[_buy_pos("AAPL", 5.0, 150.0)])

        await df_node(state)
        await auditor_node(state)

        # data_fetcher calls add_position with user_id=77
        df_cmd = ps.add_position.call_args[0][0]
        assert df_cmd.user_id == 77

        # auditor calls audit with user_id=77
        query = audit_service.audit.call_args[0][0]
        assert query.user_id == 77
