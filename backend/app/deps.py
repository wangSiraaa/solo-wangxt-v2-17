from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models
from .db import get_session


@dataclass
class Identity:
    user_id: str
    role: str  # researcher | admin | participant
    name: str


def get_identity(
    session: Session = Depends(get_session),
    x_user_id: str | None = Header(default=None),
) -> Identity:
    """演示用身份解析：请求头 X-User-Id 即测试身份（如 R-101 / A-001 / P-001）。"""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id header")
    lookups = (
        (models.Researcher, "researcher", "name"),
        (models.Admin, "admin", "name"),
        (models.Participant, "participant", "label"),
    )
    for model, role, name_attr in lookups:
        row = session.get(model, x_user_id)
        if row is not None:
            return Identity(user_id=x_user_id, role=role, name=getattr(row, name_attr))
    raise HTTPException(status_code=401, detail=f"unknown identity: {x_user_id}")


def require_role(*roles: str):
    def dependency(identity: Identity = Depends(get_identity)) -> Identity:
        if identity.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"role {identity.role} not allowed, need one of {roles}",
            )
        return identity

    return dependency
