"""Authorization interfaces for source administration.

Authentication is intentionally not implemented yet. The dependency below is the seam
future auth middleware can replace while keeping mutating routes protected by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated actor placeholder used for source registry audit hooks."""

    subject: str
    roles: tuple[str, ...]
    user_id: UUID | None = None

    def has_role(self, role: str) -> bool:
        return role in self.roles


async def get_current_principal() -> Principal:
    """Return the current actor once authentication is wired in."""
    return Principal(subject="system-bootstrap", roles=("admin",))


async def require_admin(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    """RBAC dependency for administrator-only source mutations."""
    return principal

