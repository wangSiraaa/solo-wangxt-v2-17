#!/usr/bin/env bash
# 端到端演示：授予 -> 导出排队 -> 撤回 -> 链接失效 -> 并发检查点
# 前置：后端以 RUN_WORKER=0 启动（手动驱动导出队列，保证演示确定性）：
#   cd backend && RUN_WORKER=0 uvicorn app.main:app --port 8000
set -euo pipefail

API="${API:-http://localhost:8000}"
R="X-User-Id: R-101"   # 研究员
A="X-User-Id: A-001"   # 数据管理员
P="X-User-Id: P-001"   # 参与者

step() { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }
json_get() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

curl -sf "$API/api/health" > /dev/null || { echo "后端不可达：$API"; exit 1; }

step "0. 重置演示数据"
curl -s -X POST "$API/api/demo/reset" > /dev/null && echo "已重置"

step "1. 研究员 R-101 申请 DS-CARDIO-2024（用途：cardio）"
REQ=$(curl -s -X POST "$API/api/requests" -H "$R" -H 'Content-Type: application/json' \
  -d '{"dataset_id":"DS-CARDIO-2024","purpose_code":"cardio","project_title":"高血压风险因素分析"}')
RID=$(echo "$REQ" | json_get "d['id']")
echo "申请已提交：request #$RID"

step "2. 管理员批准，发放 7 天限时下载权限"
APPR=$(curl -s -X POST "$API/api/admin/requests/$RID/approve" -H "$A" -H 'Content-Type: application/json' -d '{"days_valid":7}')
GID=$(echo "$APPR" | json_get "d['grant_id']")
echo "授权已发放：grant #$GID，有效期至 $(echo "$APPR" | json_get "d['expires_at']")"

step "3. 研究员排队导出（随后参与者撤回 -> 排队任务被取消）"
JOB1=$(curl -s -X POST "$API/api/exports" -H "$R" -H 'Content-Type: application/json' -d "{\"grant_id\":$GID}" | json_get "d['id']")
echo "导出任务 #$JOB1 已排队"
curl -s -X POST "$API/api/participants/me/consents/cardio" -H "$P" -H 'Content-Type: application/json' -d '{"action":"withdraw"}'
echo
curl -s -X POST "$API/api/admin/worker/run" -H "$A"
echo "  <- Worker 无任务可执行：#$JOB1 已在撤回时被取消"

step "4. 参与者重新授权 -> 导出完成 -> 研究员下载"
curl -s -X POST "$API/api/participants/me/consents/cardio" -H "$P" -H 'Content-Type: application/json' -d '{"action":"grant"}' > /dev/null
JOB2=$(curl -s -X POST "$API/api/exports" -H "$R" -H 'Content-Type: application/json' -d "{\"grant_id\":$GID}" | json_get "d['id']")
curl -s -X POST "$API/api/admin/worker/run" -H "$A"; echo
TOKEN=$(curl -s "$API/api/exports/mine" -H "$R" | json_get "[e for e in d['exports'] if e['id']==$JOB2][0]['download_token']")
CODE=$(curl -s -o /tmp/rdp-download.csv -w "%{http_code}" "$API/api/downloads/$TOKEN")
echo "下载任务 #$JOB2 的 CSV：HTTP $CODE（$(wc -l < /tmp/rdp-download.csv | tr -d ' ') 行，含表头）"

step "5. 参与者再次撤回 -> 已发放的链接重新校验失败"
curl -s -X POST "$API/api/participants/me/consents/cardio" -H "$P" -H 'Content-Type: application/json' -d '{"action":"withdraw"}' > /dev/null
echo "链接校验：$(curl -s "$API/api/downloads/$TOKEN/check")"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/api/downloads/$TOKEN")
echo "再次下载同一链接：HTTP $CODE（403 = 授权已撤回，访问被拒绝并留痕）"

step "6. 并发场景：导出执行窗口内撤回 -> 提交前检查点拦截"
curl -s -X POST "$API/api/participants/me/consents/cardio" -H "$P" -H 'Content-Type: application/json' -d '{"action":"grant"}' > /dev/null
JOB3=$(curl -s -X POST "$API/api/exports" -H "$R" -H 'Content-Type: application/json' -d "{\"grant_id\":$GID}" | json_get "d['id']")
echo "导出任务 #$JOB3 已排队，后台启动 Worker（执行窗口约 3 秒）…"
curl -s -X POST "$API/api/admin/worker/run" -H "$A" > /tmp/rdp-worker.json &
WPID=$!
sleep 1   # 任务已进入执行窗口（检查点 A 已通过）
curl -s -X POST "$API/api/participants/me/consents/cardio" -H "$P" -H 'Content-Type: application/json' -d '{"action":"withdraw"}' > /dev/null
echo "参与者在执行窗口内撤回"
wait $WPID
echo "Worker 结果：$(cat /tmp/rdp-worker.json)  <- 检查点 B 拦截，任务取消，未签发链接"

step "7. 审计事件流（历史记录完整保留）"
curl -s "$API/api/admin/events?limit=12" -H "$A" | python3 -c "
import sys, json
for e in json.load(sys.stdin)['events']:
    print(f\"  #{e['id']:>2} {e['event_type']:<18} actor={e['actor_id']:<6} job={e['export_job_id'] or '-'}  {e['detail'] or ''}\")"
echo
echo "演示完成。浏览器打开 http://localhost:3000 查看三个门户。"
