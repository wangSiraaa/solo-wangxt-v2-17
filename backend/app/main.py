import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, models  # noqa: F401 - 确保模型已注册
from .db import Base, SessionLocal, engine
from .routers import admin, catalog, demo, downloads, participant, researcher
from .seed import seed
from .services.exports import worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if seed(session):  # 空库时写入样本数据
            session.commit()
    stop_event = threading.Event()
    worker_thread = None
    if config.RUN_WORKER:
        worker_thread = threading.Thread(
            target=worker_loop, args=(SessionLocal, stop_event), daemon=True
        )
        worker_thread.start()
    yield
    stop_event.set()
    if worker_thread:
        worker_thread.join(timeout=2)


app = FastAPI(title="研究数据平台 · 授权撤回演示", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(researcher.router)
app.include_router(admin.router)
app.include_router(participant.router)
app.include_router(downloads.router)
app.include_router(demo.router)


@app.get("/api/health")
def health():
    return {"ok": True}
