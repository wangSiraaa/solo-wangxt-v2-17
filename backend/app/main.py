from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import admin, downloads, participant, public, researcher

app = FastAPI(
    title="研究数据授权与撤回演示平台",
    description="授权版本化 · 限时下载授权 · 参与者撤回 · 导出/下载并发检查点（本地脱敏演示）",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)

app.include_router(public.router)
app.include_router(researcher.router)
app.include_router(admin.router)
app.include_router(participant.router)
app.include_router(downloads.router)


@app.post("/api/dev/reset")
def dev_reset():
    """仅本地演示：清空并重建数据库到 seed.sql 的初始状态。"""
    settings = get_settings()
    if not settings.dev_mode:
        return {"ok": False, "message": "dev_mode 已关闭"}
    import psycopg

    from .config import get_settings as gs

    base = gs().database_url.rsplit("/", 1)[0]
    here = Path(__file__).resolve().parent.parent
    schema_sql = (here / "schema.sql").read_text(encoding="utf-8")
    seed_sql = (here / "seed.sql").read_text(encoding="utf-8")
    with psycopg.connect(base + "/postgres", autocommit=True) as admin_conn:
        admin_conn.execute("DROP DATABASE IF EXISTS consent_demo")
        admin_conn.execute("CREATE DATABASE consent_demo")
    with psycopg.connect(gs().database_url) as conn:
        conn.execute(schema_sql)
        conn.execute(seed_sql)
        conn.commit()
    # 清空旧导出文件
    for f in Path(settings.export_dir).glob("*.csv"):
        f.unlink()
    return {"ok": True, "message": "已重置为初始演示状态"}
