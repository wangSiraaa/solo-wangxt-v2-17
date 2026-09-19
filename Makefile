PY ?= .venv/bin/python

.PHONY: install backend backend-manual frontend test demo

install:            ## 安装后端依赖到 .venv
	python3 -m venv .venv && $(PY) -m pip install -r backend/requirements.txt

backend:            ## 启动后端（后台导出 Worker 开启）
	cd backend && DATABASE_URL="sqlite:///./dev.db" RUN_WORKER=1 ../$(PY) -m uvicorn app.main:app --port 8000

backend-manual:     ## 启动后端（关闭后台 Worker，供 scripts/demo.sh 手动驱动）
	cd backend && DATABASE_URL="sqlite:///./dev.db" RUN_WORKER=0 ../$(PY) -m uvicorn app.main:app --port 8000

frontend:           ## 启动前端
	cd frontend && npm install && API_URL=http://localhost:8000 NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev

test:               ## 运行后端测试
	cd backend && ../$(PY) -m pytest -q

demo:               ## 运行端到端演示脚本（需先 make backend-manual）
	API=http://localhost:8000 bash scripts/demo.sh
