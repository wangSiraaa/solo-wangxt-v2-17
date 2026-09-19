#!/usr/bin/env python3
"""导出队列 worker（与 FastAPI 同代码、不同进程）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.exporter import run_worker_loop  # noqa: E402

if __name__ == "__main__":
    print("export worker started")
    run_worker_loop()
