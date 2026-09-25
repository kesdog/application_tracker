"""Small stable error vocabulary for the agent transports only."""
from dataclasses import dataclass


@dataclass
class AgentApiError(Exception):
    code: str
    message: str
    status_code: int = 400

    def payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


def from_exception(exc: Exception) -> AgentApiError:
    if isinstance(exc, AgentApiError):
        return exc
    name = exc.__class__.__name__
    message = str(exc) or "Agent operation failed"
    lower = message.lower()
    if name == "ApplicationNotFound":
        if "interview" in lower:
            code = "INTERVIEW_NOT_FOUND"
        elif "task" in lower:
            code = "TASK_NOT_FOUND"
        elif "follow-up" in lower or "followup" in lower:
            code = "FOLLOWUP_NOT_FOUND"
        else:
            code = "APPLICATION_NOT_FOUND"
        return AgentApiError(code, message, 404)
    if name == "IdempotencyConflict":
        return AgentApiError("IDEMPOTENCY_CONFLICT", message, 409)
    if "job url or an email reference" in lower:
        return AgentApiError("SOURCE_REQUIRED", message, 422)
    if "outcome requires status" in lower or "reopen this application" in lower:
        return AgentApiError("INVALID_STATE_TRANSITION", message, 409)
    if name in {"ValidationError", "InvalidApplication", "ValueError", "KeyError"}:
        return AgentApiError("VALIDATION_ERROR", message, 422)
    return AgentApiError("AGENT_OPERATION_FAILED", message, 500)
