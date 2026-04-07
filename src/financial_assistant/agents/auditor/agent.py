import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import AuditPortfolioQuery
from financial_assistant.application.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def make_auditor_node(audit_service: AuditService):  # type: ignore[no-untyped-def]
    async def auditor_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        user_id = state["user_id"]
        period = state.get("period", "1y")

        try:
            query = AuditPortfolioQuery(user_id=user_id, period=period)
            report = await audit_service.audit(query)
            return {"audit_report": report, "error": None}
        except Exception as exc:
            logger.error("Auditor failed for user %s: %s", user_id, exc)
            return {"audit_report": None, "error": str(exc)}

    return auditor_node
