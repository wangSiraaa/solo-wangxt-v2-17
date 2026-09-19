from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres@127.0.0.1:5433/consent_demo"
    export_dir: str = "/workspace/backend/data/exports"
    # 导出任务“排队→生成”的模拟耗时（秒）：用于演示撤回与导出并发时的检查点
    export_processing_seconds: float = 8.0
    worker_poll_seconds: float = 1.0
    # 管理员批准时默认的限时下载窗口（分钟）
    default_grant_minutes: int = 30
    dev_mode: bool = True

    class Config:
        env_prefix = "CONSENT_"
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
