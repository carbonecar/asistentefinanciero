"""
Unit tests for graph routing functions and quant_node sentiment warning.

Covers:
- route_by_intent:  supervisor → specialist dispatch (blocking vs non-blocking)
- post_fetch_route: post-blocker dispatch (remaining intents or fx_fetcher)
- quant_node:       warning when use_sentiment=True but news_results unavailable

No LangGraph execution, no DB, no network — only unittest.mock.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from financial_assistant.agents.graph import post_fetch_route, route_by_intent
from financial_assistant.agents.state import Node
from financial_assistant.domain.models.analysis import OptimizedWeights, QuantResult
from financial_assistant.domain.models.news import SentimentResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(
    intents: list[str],
    use_sentiment: bool = False,
    news_results: list[SentimentResult] | None = None,
) -> dict:  # type: ignore[type-arg]
    return {
        "user_id": 1,
        "user_message": "",
        "messages": [],
        "intents": intents,
        "active_tickers": ["AAPL"],
        "period": "1y",
        "use_sentiment": use_sentiment,
        "positions": [],
        "market_data_result": None,
        "audit_report": None,
        "quant_result": None,
        "news_results": news_results,
        "exchange_rates": None,
        "final_response": None,
        "errors": [],
    }


def _make_weights() -> OptimizedWeights:
    return OptimizedWeights(
        weights={"AAPL": 1.0},
        expected_annual_return=0.1,
        annual_volatility=0.2,
        sharpe_ratio=0.5,
    )


def _make_sentiment(ticker: str = "AAPL") -> SentimentResult:
    return SentimentResult(
        ticker=ticker,
        score=0.5,
        label="positive",
        article_count=3,
        representative_headlines=("Headline A", "Headline B"),
    )


# ---------------------------------------------------------------------------
# route_by_intent
# ---------------------------------------------------------------------------


class TestRouteByIntent:
    # --- single intent: each intent routes to its designated node ---

    def test_news_alone_routes_to_news_scout(self):
        assert route_by_intent(_state(["news"])) == [Node.NEWS_SCOUT]

    def test_optimize_alone_routes_to_quant(self):
        assert route_by_intent(_state(["optimize"])) == [Node.QUANT]

    def test_audit_alone_routes_to_auditor(self):
        assert route_by_intent(_state(["audit"])) == [Node.AUDITOR]

    def test_data_fetch_alone_routes_to_data_fetcher(self):
        assert route_by_intent(_state(["data_fetch"])) == [Node.DATA_FETCHER]

    def test_general_routes_to_fx_fetcher(self):
        # "general" → UX_AGENT → ROUTING_OVERRIDES → FX_FETCHER
        assert route_by_intent(_state(["general"])) == [Node.FX_FETCHER]

    def test_unsupported_routes_to_unsupported_node(self):
        assert route_by_intent(_state(["unsupported"])) == [Node.UNSUPPORTED]

    def test_empty_intents_falls_back_to_unsupported(self):
        assert route_by_intent(_state([])) == [Node.UNSUPPORTED]

    # --- "news" is blocking: when mixed with non-blocking, only news_scout dispatched ---

    def test_news_plus_optimize_dispatches_only_news_scout(self):
        result = route_by_intent(_state(["news", "optimize"]))
        assert result == [Node.NEWS_SCOUT]

    def test_news_plus_audit_dispatches_only_news_scout(self):
        result = route_by_intent(_state(["news", "audit"]))
        assert result == [Node.NEWS_SCOUT]

    def test_news_plus_optimize_plus_audit_dispatches_only_news_scout(self):
        result = route_by_intent(_state(["news", "optimize", "audit"]))
        assert result == [Node.NEWS_SCOUT]

    def test_quant_not_dispatched_when_news_is_blocking(self):
        result = route_by_intent(_state(["news", "optimize"]))
        assert Node.QUANT not in result

    # --- "data_fetch" is blocking: original behavior preserved ---

    def test_data_fetch_plus_optimize_dispatches_only_data_fetcher(self):
        result = route_by_intent(_state(["data_fetch", "optimize"]))
        assert result == [Node.DATA_FETCHER]

    def test_data_fetch_plus_audit_dispatches_only_data_fetcher(self):
        result = route_by_intent(_state(["data_fetch", "audit"]))
        assert result == [Node.DATA_FETCHER]

    # --- both blockers present: dispatched in parallel ---

    def test_data_fetch_and_news_both_dispatched_when_together(self):
        result = route_by_intent(_state(["data_fetch", "news", "optimize"]))
        assert set(result) == {Node.DATA_FETCHER, Node.NEWS_SCOUT}
        assert len(result) == 2

    def test_only_blockers_dispatched_when_non_blocking_also_present(self):
        result = route_by_intent(_state(["data_fetch", "news", "optimize"]))
        assert Node.QUANT not in result

    # --- pure non-blocking: all dispatched in parallel ---

    def test_optimize_and_audit_both_dispatched(self):
        result = route_by_intent(_state(["optimize", "audit"]))
        assert set(result) == {Node.QUANT, Node.AUDITOR}

    def test_news_alone_is_not_treated_as_non_blocking(self):
        # "news" alone: blocking=["news"], non_blocking=[] → else branch → [NEWS_SCOUT]
        # quant must NOT appear
        result = route_by_intent(_state(["news"]))
        assert Node.QUANT not in result
        assert result == [Node.NEWS_SCOUT]

    # --- optimize + use_sentiment=True: routes to news_scout FIRST (no news yet) ---

    def test_optimize_with_sentiment_routes_to_news_scout(self):
        result = route_by_intent(_state(["optimize"], use_sentiment=True))
        assert result == [Node.NEWS_SCOUT]

    def test_optimize_with_sentiment_does_not_route_to_quant_directly(self):
        result = route_by_intent(_state(["optimize"], use_sentiment=True))
        assert Node.QUANT not in result

    def test_optimize_with_sentiment_false_routes_to_quant(self):
        result = route_by_intent(_state(["optimize"], use_sentiment=False))
        assert result == [Node.QUANT]

    def test_optimize_and_audit_with_sentiment_routes_to_news_scout_and_auditor(self):
        result = route_by_intent(_state(["optimize", "audit"], use_sentiment=True))
        assert set(result) == {Node.NEWS_SCOUT, Node.AUDITOR}

    def test_news_blocking_overrides_sentiment_routing(self):
        # When "news" is blocking, the sentiment-redirect of optimize doesn't apply.
        # Only the blocker (news_scout) is dispatched in this round.
        result = route_by_intent(_state(["news", "optimize"], use_sentiment=True))
        assert result == [Node.NEWS_SCOUT]
        assert Node.QUANT not in result

    def test_all_route_by_intent_destinations_are_valid_graph_nodes(self):
        valid_nodes = {
            Node.DATA_FETCHER, Node.AUDITOR, Node.QUANT,
            Node.NEWS_SCOUT, Node.FX_FETCHER, Node.UNSUPPORTED,
        }
        test_cases = [
            (["audit"], False),
            (["optimize"], False),
            (["optimize"], True),
            (["news"], False),
            (["data_fetch"], False),
            (["general"], False),
            (["unsupported"], False),
            (["audit", "optimize"], False),
            (["news", "optimize"], False),
            (["news", "optimize"], True),
            (["data_fetch", "audit"], False),
            (["optimize", "audit"], True),
        ]
        for intents, use_sentiment in test_cases:
            destinations = route_by_intent(_state(intents, use_sentiment=use_sentiment))
            for dest in destinations:
                label = f"{intents} use_sentiment={use_sentiment}"
                assert dest in valid_nodes, f"Node '{dest}' not in graph map for {label}"


# ---------------------------------------------------------------------------
# post_fetch_route
# ---------------------------------------------------------------------------


class TestPostFetchRoute:
    # --- news alone: no remaining intents → fx_fetcher ---

    def test_news_alone_routes_to_fx_fetcher(self):
        assert post_fetch_route(_state(["news"])) == [Node.FX_FETCHER]

    def test_data_fetch_alone_routes_to_fx_fetcher(self):
        assert post_fetch_route(_state(["data_fetch"])) == [Node.FX_FETCHER]

    # --- news + optimize: quant is the remaining non-blocking intent ---

    def test_news_plus_optimize_routes_to_quant(self):
        assert post_fetch_route(_state(["news", "optimize"])) == [Node.QUANT]

    def test_news_plus_optimize_does_not_route_to_news_scout(self):
        result = post_fetch_route(_state(["news", "optimize"]))
        assert Node.NEWS_SCOUT not in result

    # --- news + audit: auditor is the remaining non-blocking intent ---

    def test_news_plus_audit_routes_to_auditor(self):
        assert post_fetch_route(_state(["news", "audit"])) == [Node.AUDITOR]

    # --- news + optimize + audit: both non-blocking dispatched in parallel ---

    def test_news_plus_optimize_plus_audit_routes_to_both(self):
        result = post_fetch_route(_state(["news", "optimize", "audit"]))
        assert set(result) == {Node.QUANT, Node.AUDITOR}
        assert len(result) == 2

    # --- data_fetch + news + optimize: both blockers ran, quant remains ---

    def test_data_fetch_plus_news_plus_optimize_routes_to_quant(self):
        result = post_fetch_route(_state(["data_fetch", "news", "optimize"]))
        assert result == [Node.QUANT]

    # --- original data_fetch behavior preserved ---

    def test_data_fetch_plus_optimize_routes_to_quant(self):
        assert post_fetch_route(_state(["data_fetch", "optimize"])) == [Node.QUANT]

    def test_data_fetch_plus_audit_routes_to_auditor(self):
        assert post_fetch_route(_state(["data_fetch", "audit"])) == [Node.AUDITOR]

    # --- "general" inside remaining resolves to fx_fetcher via ROUTING_OVERRIDES ---

    def test_news_plus_general_remaining_routes_to_fx_fetcher(self):
        # "general" → UX_AGENT → ROUTING_OVERRIDES → FX_FETCHER
        result = post_fetch_route(_state(["news", "general"]))
        assert result == [Node.FX_FETCHER]

    # --- "news" and "data_fetch" are excluded from remaining (they are blockers) ---

    def test_blockers_never_appear_in_remaining(self):
        result = post_fetch_route(_state(["news", "data_fetch", "optimize"]))
        assert Node.NEWS_SCOUT not in result
        assert Node.DATA_FETCHER not in result

    # --- optimize + use_sentiment=True: after news_scout, post_fetch routes to QUANT ---
    # post_fetch uses _resolve (not _resolve_destination), so no sentiment re-routing.

    def test_optimize_with_sentiment_post_fetch_routes_to_quant(self):
        result = post_fetch_route(_state(["optimize"], use_sentiment=True))
        assert result == [Node.QUANT]

    def test_optimize_with_sentiment_post_fetch_does_not_loop_to_news_scout(self):
        result = post_fetch_route(_state(["optimize"], use_sentiment=True))
        assert Node.NEWS_SCOUT not in result

    def test_news_optimize_with_sentiment_post_fetch_routes_to_quant(self):
        # After news_scout ran for ["news", "optimize"] with use_sentiment=True,
        # post_fetch should send remaining "optimize" → QUANT (not back to NEWS_SCOUT).
        result = post_fetch_route(_state(["news", "optimize"], use_sentiment=True))
        assert result == [Node.QUANT]
        assert Node.NEWS_SCOUT not in result


# ---------------------------------------------------------------------------
# quant_node — sentiment warning
# ---------------------------------------------------------------------------


class TestQuantNodeSentimentWarning:
    def _make_node(self, sentiment_adjusted: bool = False) -> tuple:
        mock_result = QuantResult(
            user_id=1,
            optimized_weights=_make_weights(),
            sentiment_adjusted=sentiment_adjusted,
        )
        mock_service = MagicMock()
        mock_service.optimize = AsyncMock(return_value=mock_result)
        from financial_assistant.agents.quant.agent import make_quant_node

        return make_quant_node(mock_service), mock_result

    @pytest.mark.asyncio
    async def test_warning_fires_when_use_sentiment_true_and_news_results_none(self):
        node, _ = self._make_node()
        result = await node(_state(["optimize"], use_sentiment=True, news_results=None))
        assert len(result["errors"]) == 1
        assert "sentimiento" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_warning_fires_when_use_sentiment_true_and_news_results_empty_list(self):
        node, _ = self._make_node()
        result = await node(_state(["optimize"], use_sentiment=True, news_results=[]))
        assert len(result["errors"]) == 1
        assert "sentimiento" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_no_warning_when_news_results_available(self):
        node, _ = self._make_node(sentiment_adjusted=True)
        news = [_make_sentiment("AAPL")]
        result = await node(_state(["news", "optimize"], use_sentiment=True, news_results=news))
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_no_warning_when_use_sentiment_false_and_no_news(self):
        node, _ = self._make_node()
        result = await node(_state(["optimize"], use_sentiment=False, news_results=None))
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_quant_result_returned_even_when_warning_fires(self):
        node, _ = self._make_node()
        result = await node(_state(["optimize"], use_sentiment=True, news_results=None))
        assert result["quant_result"] is not None

    @pytest.mark.asyncio
    async def test_sentiment_adjusted_true_when_news_available(self):
        node, _ = self._make_node(sentiment_adjusted=True)
        news = [_make_sentiment("AAPL")]
        result = await node(_state(["news", "optimize"], use_sentiment=True, news_results=news))
        assert result["quant_result"].sentiment_adjusted is True

    @pytest.mark.asyncio
    async def test_warning_and_exception_both_reported(self):
        mock_service = MagicMock()
        mock_service.optimize = AsyncMock(side_effect=RuntimeError("optimizer crash"))
        from financial_assistant.agents.quant.agent import make_quant_node

        node = make_quant_node(mock_service)
        result = await node(_state(["optimize"], use_sentiment=True, news_results=None))
        assert result["quant_result"] is None
        assert len(result["errors"]) == 2
        assert any("sentimiento" in e for e in result["errors"])
        assert any("optimizer crash" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_service_exception_without_sentiment_flag_reports_only_exception(self):
        mock_service = MagicMock()
        mock_service.optimize = AsyncMock(side_effect=RuntimeError("DB error"))
        from financial_assistant.agents.quant.agent import make_quant_node

        node = make_quant_node(mock_service)
        result = await node(_state(["optimize"], use_sentiment=False, news_results=None))
        assert result["quant_result"] is None
        assert len(result["errors"]) == 1
        assert "DB error" in result["errors"][0]
