from fastapi import APIRouter

from ..db import Base, SessionLocal, engine
from ..seed import seed

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reset")
def reset_demo():
    """重置为初始样本数据（仅本地演示环境使用）。"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)
        session.commit()
    return {"ok": True}
