"""
Unit tests para el flujo de ventas/salidas en data_fetcher_node.

Cubre:
- Salida total: sell_qty >= existing_qty → remove_position()
- Salida parcial: sell_qty < existing_qty → add_position() con qty reducida
- Posición inexistente: log de warning, sin llamadas a remove/add
- sell_qty == existing_qty tratado como salida total
- quantity=999999 (señal de salida total) tratado como salida total
- Costo promedio de la posición original se preserva en salida parcial
- action="SELL" (mayúsculas) reconocido correctamente
- Compra sin precio (avg_cost_usd=0) es ignorada — no se mezcla con sells

No se conecta a DB ni red. Todos los servicios son AsyncMock.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from financial_assistant.agents.data_fetcher.agent import make_data_fetcher_node
from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _position(ticker: str = "AAPL", quantity: float = 10.0, avg_cost: float = 150.0) -> Position:
    return Position(
        ticker=ticker,
        asset_type=AssetType.STOCK,
        quantity=Decimal(str(quantity)),
        avg_cost_usd=Decimal(str(avg_cost)),
    )


def _portfolio(*positions: Position, user_id: int = 42) -> Portfolio:
    return Portfolio(user_id=user_id, positions=list(positions))


def _portfolio_service(portfolio: Portfolio | None = None) -> MagicMock:
    svc = MagicMock()
    svc.get_or_create = AsyncMock(return_value=portfolio or _portfolio())
    svc.remove_position = AsyncMock()
    svc.add_position = AsyncMock()
    return svc


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


def _sell_pos(ticker: str = "AAPL", quantity: float = 5.0, avg_cost_usd: float = 200.0) -> dict:
    return {
        "ticker": ticker, "quantity": quantity, "avg_cost_usd": avg_cost_usd,
        "asset_type": "stock", "action": "sell",
    }


# ---------------------------------------------------------------------------
# Salida total (sell_qty >= existing_qty)
# ---------------------------------------------------------------------------


class TestFullExit:
    @pytest.mark.asyncio
    async def test_full_exit_calls_remove_position(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=10.0)]))

        ps.remove_position.assert_called_once_with(42, "AAPL")

    @pytest.mark.asyncio
    async def test_full_exit_does_not_call_add_position(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=10.0)]))

        ps.add_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_qty_greater_than_held_is_full_exit(self):
        portfolio = _portfolio(_position("AAPL", quantity=5.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=999999.0)]))

        ps.remove_position.assert_called_once_with(42, "AAPL")

    @pytest.mark.asyncio
    async def test_sell_qty_equal_to_held_is_full_exit(self):
        portfolio = _portfolio(_position("AAPL", quantity=7.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=7.0)]))

        ps.remove_position.assert_called_once_with(42, "AAPL")


# ---------------------------------------------------------------------------
# Salida parcial (sell_qty < existing_qty)
# ---------------------------------------------------------------------------


class TestPartialExit:
    @pytest.mark.asyncio
    async def test_partial_exit_calls_add_position_not_remove(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0, avg_cost=150.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=3.0)]))

        ps.add_position.assert_called_once()
        ps.remove_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_exit_reduces_quantity_correctly(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0, avg_cost=150.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=3.0)]))

        cmd = ps.add_position.call_args[0][0]
        assert cmd.quantity == Decimal("7")

    @pytest.mark.asyncio
    async def test_partial_exit_preserves_cost_basis(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0, avg_cost=150.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        # El precio de venta (200) no debe reemplazar el costo promedio original (150)
        await node(_state(positions=[_sell_pos("AAPL", quantity=4.0, avg_cost_usd=200.0)]))

        cmd = ps.add_position.call_args[0][0]
        assert cmd.avg_cost_usd == Decimal("150")

    @pytest.mark.asyncio
    async def test_partial_exit_preserves_asset_type(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=2.0)]))

        cmd = ps.add_position.call_args[0][0]
        assert cmd.asset_type == AssetType.STOCK


# ---------------------------------------------------------------------------
# Posición inexistente al momento de la venta
# ---------------------------------------------------------------------------


class TestSellWithNoExistingPosition:
    @pytest.mark.asyncio
    async def test_sell_without_existing_position_skips(self):
        portfolio = _portfolio()  # cartera vacía
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        await node(_state(positions=[_sell_pos("AAPL", quantity=5.0)]))

        ps.remove_position.assert_not_called()
        ps.add_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_without_existing_position_does_not_raise(self):
        portfolio = _portfolio()
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        result = await node(_state(positions=[_sell_pos("AAPL", quantity=5.0)]))

        assert result is not None


# ---------------------------------------------------------------------------
# Robustez — action case-insensitive, buy sin precio ignorado
# ---------------------------------------------------------------------------


class TestSellEdgeCases:
    @pytest.mark.asyncio
    async def test_action_sell_uppercase_recognized(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        pos = {**_sell_pos("AAPL", quantity=10.0), "action": "SELL"}
        await node(_state(positions=[pos]))

        ps.remove_position.assert_called_once_with(42, "AAPL")

    @pytest.mark.asyncio
    async def test_buy_without_price_is_skipped_not_confused_with_sell(self):
        portfolio = _portfolio(_position("AAPL", quantity=10.0))
        ps = _portfolio_service(portfolio)
        node = make_data_fetcher_node(_market_service(), ps)

        buy_no_price = {"ticker": "AAPL", "quantity": 5.0, "avg_cost_usd": 0, "asset_type": "stock", "action": "buy"}
        await node(_state(positions=[buy_no_price]))

        ps.add_position.assert_not_called()
        ps.remove_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_and_buy_in_same_request_both_processed(self):
        portfolio = _portfolio(_position("MSFT", quantity=10.0, avg_cost=300.0))
        ps = _portfolio_service(portfolio)

        msft_record = MagicMock()
        msft_record.close = Decimal("310")
        msft_record.date = __import__("datetime").date(2024, 1, 2)
        mkt = MagicMock()
        mkt.fetch_and_persist = AsyncMock(return_value={"AAPL": [], "MSFT": [msft_record]})

        node = make_data_fetcher_node(mkt, ps)

        positions = [
            {"ticker": "AAPL", "quantity": 5.0, "avg_cost_usd": 180.0, "asset_type": "stock", "action": "buy"},
            _sell_pos("MSFT", quantity=10.0),
        ]
        await node(_state(active_tickers=["AAPL", "MSFT"], positions=positions))

        ps.add_position.assert_called_once()
        buy_cmd = ps.add_position.call_args[0][0]
        assert buy_cmd.ticker == "AAPL"
        assert buy_cmd.avg_cost_usd == Decimal("180")

        ps.remove_position.assert_called_once_with(42, "MSFT")
