from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.core.security import CurrentUser


DEFAULT_TENANT_ID = "default"
DEFAULT_WORKSPACE_ID = "default"
DEFAULT_AGENT_ID = "ai_assistant"


@dataclass(frozen=True)
class IdentityContext:
    """Authoritative identity propagated through assistant persistence."""

    tenant_id: str
    workspace_id: str
    user_id: str
    role_ids: tuple[str, ...]
    agent_id: str = DEFAULT_AGENT_ID
    session_id: str = ""
    run_id: str = "latest"

    @classmethod
    def from_user(
        cls,
        user: CurrentUser,
        *,
        session_id: str = "",
        run_id: str = "latest",
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> "IdentityContext":
        context = cls(
            tenant_id=user.tenant_id,
            workspace_id=user.workspace_id,
            user_id=user.user_id,
            role_ids=tuple(user.role_ids or (user.role,)),
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
        )
        context.require_valid(require_session=False)
        return context

    def with_session(self, session_id: str, run_id: str | None = None) -> "IdentityContext":
        context = replace(self, session_id=session_id, run_id=run_id or self.run_id)
        context.require_valid(require_session=True)
        return context

    def require_valid(self, *, require_session: bool = True) -> None:
        required = {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
        }
        if require_session:
            required["session_id"] = self.session_id
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError(f"identity context missing: {', '.join(missing)}")
