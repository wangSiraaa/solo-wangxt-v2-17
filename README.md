# 研究数据平台 · 授权撤回演示

参与者撤回授权后，平台**准确停止其数据的未来使用**，同时完整保留历史访问记录。
三个角色、两个服务、一套权限检查点机制：

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  研究员门户   │   │ 数据管理员    │   │  参与者门户   │
│ /researcher  │   │   /admin     │   │ /participant │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       └──────────────────┼──────────────────┘
                          ▼
               Next.js 前端 (3000)
                          ▼
               FastAPI 权限判断 (8000)
        ┌──────────┬───────────┬───────────┐
        ▼          ▼           ▼           ▼
   授权版本链   申请/限时授权  导出队列    不可变审计
        └──────────┴───────────┴───────────┘
                          ▼
                PostgreSQL (5432)
```

## 核心语义

**撤回授权（按参与者 × 用途）产生四个效果：**

| 对象 | 行为 | 实现 |
|---|---|---|
| 历史访问记录 | **保留**，永不删除 | `access_events` 只追加 |
| 尚未执行的导出任务 | **立即取消** | 撤回事务内将 `queued` 任务置为 `cancelled` |
| 执行中的导出任务 | **提交前检查点拦截** | Worker 在执行前/提交前各校验一次（checkpoint A/B） |
| 已发放的下载链接 | **每次访问重新校验** | `GET /api/downloads/{token}` 实时评估授权，拒绝返回 403 |

**权限判断的唯一规则**（`backend/app/services/permissions.py`）：授权未过期 **且**
数据集内每位参与者对该用途的当前授权版本都是 `granted`。排队、执行、下载全部走这一个判定函数。

**并发边界**：PostgreSQL 下 Worker 认领任务与提交前校验使用 `SELECT ... FOR UPDATE` 行锁，
与撤回事务（写 `consent_versions` + 更新 `queued` 任务）互斥；导出文件生成时还会逐行过滤
未授权参与者的数据（纵深防御）。

## 快速开始

### 方式一：Docker Compose（PostgreSQL）

```bash
docker compose up --build
# 前端 http://localhost:3000   后端 http://localhost:8000/docs
```

### 方式二：本地开发（SQLite，无需 Docker）

```bash
make install          # python3 -m venv .venv && pip install -r backend/requirements.txt
make backend          # 终端 1：FastAPI（后台导出 Worker 开启）
make frontend         # 终端 2：Next.js（首次自动 npm install）
```

### 运行端到端演示脚本

```bash
make backend-manual   # 关闭后台 Worker，手动驱动导出队列（保证演示确定性）
make demo             # 另一个终端：授予 -> 排队 -> 撤回 -> 链接失效 -> 并发检查点
```

### 运行测试

```bash
make test   # 10 个用例：版本链 / 撤回取消导出 / 检查点并发 / 链接重新校验 / 审计保留
```

## 测试身份（请求头 `X-User-Id`，前端右上角可切换）

| 身份 | ID | 说明 |
|---|---|---|
| 研究员 | `R-101` / `R-102` | 申请访问、排队导出、下载 |
| 数据管理员 | `A-001` | 审批申请、发放限时授权、查看审计 |
| 参与者 | `P-001` ~ `P-010` | 按用途授权/撤回、查看受影响项目 |

样本数据全部为本地生成的脱敏虚构数据（`backend/app/seed.py`）：
数据集 `DS-CARDIO-2024`（P-001~P-006）、`DS-METAB-2024`（P-004~P-010）；
用途 `cardio` / `diabetes` / `genomics`。

## 演示流程（与 `scripts/demo.sh` 一致）

1. **申请**：研究员门户提交「DS-CARDIO-2024 · 心血管研究」访问申请
2. **授予**：管理员批准并发放 7 天限时下载权限
3. **导出排队**：研究员点击「排队导出」→ 任务 `queued`
4. **撤回**：参与者门户（P-001）撤回「心血管研究」→ 排队任务立即取消，页面提示受影响项目
5. **重新授权 → 导出完成**：Worker 执行（检查点 A/B 通过）→ 签发 72 小时下载链接
6. **下载**：研究员下载 CSV（导出列表显示「已下载」，与「未下载」区分）
7. **再次撤回 → 链接失效**：同一链接再次访问返回 403「参与者已撤回授权」；「校验链接」按钮可实时查看
8. **并发场景**：导出执行窗口（默认 3 秒）内撤回 → 提交前检查点取消任务、删除半成品文件、不签发链接
9. **审计**：管理员事件流中，`download_served` 与 `download_denied` 并存，历史记录完整

## 数据模型（PostgreSQL）

| 表 | 作用 |
|---|---|
| `consent_versions` | 授权版本链：`(participant, purpose, version)` 唯一，只追加 |
| `access_requests` / `grants` | 研究员申请 / 管理员发放的限时授权（`expires_at`） |
| `export_jobs` | 导出任务：`queued → running → completed / cancelled` |
| `download_links` | 下载链接（token + 过期时间），访问时重新校验 |
| `access_events` | 不可变审计：申请、授权、导出、下载成功/拒绝、授权变更 |
| `datasets` / `dataset_records` / `participants` | 脱敏样本数据 |
| `purposes` / `researchers` / `admins` | 用途类别与测试身份 |

## API 摘要

```
POST /api/requests                          研究员申请访问
GET  /api/requests/mine                     我的申请
POST /api/exports                           排队导出（入队即校验授权）
GET  /api/exports/mine                      我的导出（含 downloaded 标志与链接）
POST /api/admin/requests/{id}/approve       批准并发放限时授权 {days_valid}
POST /api/admin/requests/{id}/deny          拒绝
POST /api/admin/worker/run                  手动执行导出队列
GET  /api/admin/events                      审计事件流
GET  /api/participants/me/overview          我的授权 + 受影响项目 + 撤回影响预估
POST /api/participants/me/consents/{code}   授权/撤回 {action: grant|withdraw}
GET  /api/participants/me/events            我的数据访问历史
GET  /api/downloads/{token}                 下载（每次访问重新校验，403 + 审计）
GET  /api/downloads/{token}/check           仅校验不下载（前端「校验链接」）
POST /api/demo/reset                        重置样本数据
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./dev.db` | 生产：`postgresql+psycopg2://...` |
| `RUN_WORKER` | `1` | 后台导出 Worker 开关（演示脚本用 `0`） |
| `EXPORT_WORKER_INTERVAL_SECONDS` | `4` | Worker 轮询间隔 |
| `EXPORT_WORKER_DELAY_SECONDS` | `3` | 导出执行窗口，用于观察撤回/导出并发 |
| `DOWNLOAD_LINK_TTL_HOURS` | `72` | 下载链接有效期 |
| `API_URL` / `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 前端服务端 / 浏览器访问后端的地址 |

## 目录结构

```
backend/app/
  models.py               数据模型（授权版本链、导出、链接、审计）
  services/permissions.py 权限判断唯一入口
  services/consent.py     授权/撤回（取消排队导出）
  services/exports.py     导出队列 + 双检查点 Worker
  routers/                catalog / researcher / admin / participant / downloads / demo
  seed.py                 脱敏样本数据与测试身份
backend/tests/            10 个 pytest 用例
frontend/app/             Next.js 三个门户 + 首页
scripts/demo.sh           端到端演示脚本
docker-compose.yml        PostgreSQL + 后端 + 前端
```
