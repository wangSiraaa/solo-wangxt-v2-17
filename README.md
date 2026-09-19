# 研究数据授权与撤回演示平台

一个本地可运行的端到端演示：研究员申请数据集访问 → 数据管理员**按用途**授予
**限时下载权限** → 导出任务排队执行 → 参与者通过**独立入口按用途撤回授权** →
未完成导出被取消、已发下载链接再次访问时重新校验并失效。全部访问历史只追加、
不删除。

- **后端**：FastAPI + PostgreSQL 15（权限判断、授权版本、导出队列 worker）
- **前端**：Next.js 14（App Router）展示授权范围、受影响项目、已下载/尚未下载区别
- **数据**：虚构的区间化脱敏样本（年龄段、指标区间，无姓名/联系方式/精确日期）

---

## 一、快速开始

### 方式 A：一键脚本（推荐，含免 root 的 PostgreSQL）

```bash
scripts/start_demo.sh --reset   # 首次运行：装 Python 依赖 + 本地 PG + 初始化 + 启动全部服务
scripts/demo_walkthrough.sh     # 命令行跑一遍完整闭环
scripts/stop_demo.sh            # 停止（--with-db 同时停 PostgreSQL）
```

服务地址：

| 服务 | 地址 |
| --- | --- |
| 前端（操作界面） | http://127.0.0.1:3000 |
| FastAPI / OpenAPI | http://127.0.0.1:8000/docs |
| PostgreSQL | 127.0.0.1:5433（trust 认证，仅本地） |

> `scripts/setup_postgres_local.sh` 会把 postgresql-15 的 deb 包下载解包到
> `.localpg/`（不需要 root），数据目录 `.localpg/data`。

### 方式 B：手动

```bash
# 1) 数据库（任意可用的 PostgreSQL 15；连接串可用 CONSENT_DATABASE_URL 覆盖）
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
python backend/init_db.py

# 2) 后端 API
cd backend && uvicorn app.main:app --port 8000

# 3) 导出 worker（另开终端；默认模拟 8 秒生成耗时用于演示并发）
cd backend && python run_worker.py

# 4) 前端
cd frontend && npm install && npm run build && npm run start
```

重置演示数据（不清服务）：`POST /api/dev/reset`。

运行测试：

```bash
cd backend && python -m pytest tests/ -q     # 12 个用例，含真实线程并发测试
```

---

## 二、测试身份（本地演示登录）

无密码，前端右上角下拉框切换；API 通过 `X-Test-Identity` 头指定。

| identity_key | 角色 | 用途 |
| --- | --- | --- |
| `participant-1001` … `participant-1004` | 参与者 | 独立撤回入口、查看授权版本与受影响项目 |
| `researcher-2001` / `researcher-2002` | 研究员 | 提交申请、发起导出、下载 |
| `admin-3001` | 数据管理员 | 按用途批准/拒绝、授予限时窗口、监控队列 |

初始授权（`backend/seed.sql`）：

- 用途 1「糖尿病风险因素研究」：4 名参与者全部授予；
- 用途 2「心血管风险预测研究」：P-1001、P-1003 授予；P-1004 已有
  granted v1 → withdrawn v2 的版本历史，用于直接展示撤回状态。

---

## 三、浏览器演示路径

1. 用 **R-2001** 打开「新建申请」，选择脱敏数据集 + 用途（可看到当前授予人数），提交。
2. 切换 **A-3001**：审批页批准并填写限时窗口分钟数（默认 30）。
3. 回到 **R-2001** 的项目页「发起新导出」：任务进入 **排队中 → 生成中**
   （页面轮询；生成持续约 8 秒，期间可观察“尚未产出文件”的状态）。
4. 任务变成 **已生成·尚未下载**，点「下载 CSV（实时校验授权）」，
   状态变为 **已生成·已下载**（历史下载事实之后会保留）。
5. 切换 **P-1001**：参与者页按用途展示当前授权、版本历史、**受影响的研究项目**
   （每个项目下标注排队/已生成/已取消，已生成任务标注“曾被下载/尚未下载/链接已撤销”）。
   点「撤回此用途授权」，确认弹窗会列出连带后果。
6. 回到 **R-2001**：
   - 撤回时仍在排队/生成的任务 → **已取消（participant_withdrew）**，无文件；
   - 已完成任务的链接 → **链接已失效（授权撤回后撤销）**，再点下载得到 409；
   - 再次发起导出 → CP-1 拦截（409 participant_withdrew）。
7. 「访问事件」页查看全程审计流；参与者可重新授予（新版本），但旧链接不复活、
   旧任务不恢复，必须重新发起导出。

想直接观察“生成期间撤回”，可在第 3 步任务显示「生成中」时立刻去第 5 步撤回。

---

## 四、四个权限检查点（并发正确性）

| 检查点 | 位置 | 作用 |
| --- | --- | --- |
| **CP-1** 导出入队 | `POST /researcher/projects/{id}/exports` | 申请 approved、限时窗口未过期、数据集全体参与者当前仍授予，才允许入队 |
| **CP-2** 导出执行 | `app/exporter.py::process_job` | worker **写文件之前**在数据库事务内持锁重新校验；不通过则任务 cancelled，不生成文件 |
| **CP-3** 撤回生效 | `app/consents.py::withdraw_consent` | 同一事务内：授权版本升级 → 取消 queued/running 导出 → 撤销所有相关下载链接 |
| **CP-4** 链接访问 | `GET /researcher/downloads/{token}` | **每次**访问都重新查当前授权状态（持 `consent_slots` 行锁），不使用导出时快照 |

### 锁序约定（撤回 × 导出并发）

`consent_slots` 为每个「参与者 × 用途」预置一行锁位。所有相关事务统一按
**先锁 consent_slots，再锁 export_jobs 行** 的顺序加锁：

- worker 的「拾取（只锁 job 行、立即提交）」与「执行（先锁 slots 再锁 job）」
  拆成两个事务，避免与撤回形成反向锁序导致死锁；
- 撤回与导出抢同一批 slot 锁，因此结果只有两种，且都是安全的：
  1. **撤回先拿到锁** → 导出在 CP-2 看到 withdrawn，任务 cancelled，无文件；
  2. **导出先越过 CP-2** → 文件产出，但撤回事务立即撤销其链接，
     CP-4 在下一次访问时拒绝（不存在“撤回生效后链接仍可下载”的状态）。

`backend/tests/test_flows.py::test_cp2_concurrent_withdraw_vs_export_has_verdict`
用真实双线程并发断言上述两种裁决都安全。

### 审计不随撤回删除

- `access_events` 只有 INSERT 路径（应用层无 UPDATE/DELETE）；
- 撤回后：已完成的 `export_jobs` 行、已生成 CSV、`download_links` 的
  `access_count/last_accessed_at` 全部保留，只是链接被标记 `revoked`；
- 授权变化在 `consents`（当前状态 + version）与 `consent_events`（每版一条）中留痕。

---

## 五、数据模型（PostgreSQL）

```
participants / researchers / admins / identities   身份（演示登录）
datasets / dataset_records                          脱敏样本（JSONB 区间字段）
purposes                                            用途目录
consents                     当前授权：(参与者,用途) 唯一，status + version
consent_events               授权版本历史：granted/withdrawn 每版一行
consent_slots                并发锁位：(参与者,用途)
access_requests              申请：pending/approved/rejected + grant_expires_at 限时窗口
export_jobs                  queued/running/cancelled/complete/failed，文件路径与 sha256
download_links               token、expires_at、revoked、access_count
access_events                只追加审计：申请/审批/导出/下载/拒绝/撤回
```

---

## 六、目录结构

```
backend/
  schema.sql / seed.sql       表结构与脱敏样本/测试身份
  init_db.py                  重建库并加载 schema+seed
  run_worker.py               导出队列 worker
  app/
    main.py                   FastAPI 入口（含 /api/dev/reset）
    auth.py                   演示身份（X-Test-Identity）+ 审计写入
    consents.py               CP-3 撤回事务、CP-1 可用性判断、锁位
    exporter.py               CP-2 worker 拾取/执行、CSV 物化、链接签发
    routers/                  public / researcher / admin / participant / downloads
  tests/test_flows.py         12 个端到端用例（含并发）
frontend/src/app/             Next.js 页面：研究端/管理端/参与者端/事件/样本
scripts/                      免 root PG 安装、一键启停、命令行演示
```

## 七、演示边界

这是流程与权限语义的演示实现，不是生产方案：身份用固定请求头模拟（无密码、无令牌
签发与轮换审计）、导出文件存本地磁盘、窗口过期由数据库时间判断；生产化时应替换为
真实身份提供方、对象存储 + 签名 URL、并将 worker 部署为带重试/幂等的队列消费者。
