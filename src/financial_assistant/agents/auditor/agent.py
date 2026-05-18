import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import AuditPortfolioQuery
from financial_assistant.application.services.audit_service import AuditService
from financial_assistant.domain.services.risk_rules import check_concentration

logger = logging.getLogger(__name__)


def make_auditor_node(audit_service: AuditService):  # type: ignore[no-untyped-def]
    async def auditor_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        user_id = state["user_id"]
        period = state.get("period", "1y")

        try:
            query = AuditPortfolioQuery(user_id=user_id, period=period)
            report = await audit_service.audit(query)

            risk_warnings = []
            positions_count = len(report.positions) if report and report.positions else 0
            logger.info("AUDIT_PORTFOLIO user_id=%s positions_count=%d", user_id, positions_count)
            if report and report.positions:
                total_value = sum(float(p["current_value"]) for p in report.positions)
                if total_value > 0:
                    weights = {
                        p["ticker"]: float(p["current_value"]) / total_value
                        for p in report.positions
                    }
                    risk_warnings = check_concentration(weights)

            logger.info("[Auditor] risk_warnings=%d for user %s", len(risk_warnings), user_id)
            return {"audit_report": report, "risk_warnings": risk_warnings, "errors": []}
        except Exception as exc:
            logger.error("Auditor failed for user %s: %s", user_id, exc)
            return {"audit_report": None, "errors": [str(exc)]}

    return auditor_node
