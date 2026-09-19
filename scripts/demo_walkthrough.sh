#!/usr/bin/env bash
# 命令行版完整演示（不依赖浏览器）：
#   授予 → 导出排队/完成 → 下载成功 → 参与者撤回 → 未完成导出取消/已发链接失效 → 历史保留
# 用法：scripts/demo_walkthrough.sh
set -euo pipefail
API=${API:-http://127.0.0.1:8000}
PY=python3

j() { $PY -c "import sys,json;d=json.load(sys.stdin);print(eval(\"d$1\"))"; }
H_RESEARCHER=(-H 'X-Test-Identity: researcher-2001' -H 'Content-Type: application/json')
H_ADMIN=(-H 'X-Test-Identity: admin-3001' -H 'Content-Type: application/json')
H_PARTICIPANT=(-H 'X-Test-Identity: participant-1001' -H 'Content-Type: application/json')

say() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }

say "0. 重置到初始演示状态"
curl -sS -X POST "$API/api/dev/reset" | j "['message']"

say "1. 研究员 R-2001 提交糖尿病研究用途的数据集申请"
RID=$(curl -sS -X POST "$API/api/researcher/requests" "${H_RESEARCHER[@]}" \
  -d '{"dataset_id":1,"purpose_id":1,"justification":"糖尿病风险因素逻辑回归建模"}' | j "['id']")
echo "   申请 #$RID（pending）"

say "2. 数据管理员按用途批准，授予 30 分钟限时下载窗口"
curl -sS -X POST "$API/api/admin/requests/$RID/decision" "${H_ADMIN[@]}" \
  -d '{"approve":true,"grant_minutes":30,"reviewer_note":"按用途批准"}' \
  | $PY -c "import sys,json;d=json.load(sys.stdin);print('   status=%s 窗口至 %s'%(d['status'],d['grant_expires_at']))"

say "3. 研究员发起导出（CP-1 入队检查点）"
JID=$(curl -sS -X POST "$API/api/researcher/projects/$RID/exports" -H 'X-Test-Identity: researcher-2001' | j "['id']")
echo "   导出任务 #$JID 状态 queued，等待 worker（默认生成延迟 8 秒）"
sleep 10
TOKEN=$(curl -sS "$API/api/researcher/projects/$RID" -H 'X-Test-Identity: researcher-2001' \
  | $PY -c "import sys,json;print(json.load(sys.stdin)['jobs'][0]['active_token'])")
echo "   导出完成，下载链接已签发：${TOKEN:0:18}…"

say "4. 研究员首次访问链接（CP-4 实时校验通过，下载脱敏 CSV）"
curl -sS -D - -o /tmp/walkthrough.csv -H 'X-Test-Identity: researcher-2001' \
  "$API/api/researcher/downloads/$TOKEN" | grep -iE "^HTTP|x-consent-revalidated" | sed 's/^/   /'
echo "   CSV 预览："; head -3 /tmp/walkthrough.csv | sed 's/^/   /'

say "5. 参与者 P-1001 通过独立入口撤回该用途（CP-3）"
curl -sS -X POST "$API/api/participant/consents/withdraw" "${H_PARTICIPANT[@]}" \
  -d '{"purpose_id":1,"reason":"不再希望数据用于糖尿病研究"}' \
  | $PY -c "import sys,json;d=json.load(sys.stdin);print('   撤回完成：%s v%s；取消导出 %s；撤销链接 %d 个'%(d['status'],d['version'],d['cancelled_export_ids'],len(d['revoked_link_ids'])))"

say "6. 用同一个链接再次访问 → CP-4 重新校验授权后拒绝（链接没有被缓存放行）"
curl -sS -w "\n   HTTP %{http_code}\n" -H 'X-Test-Identity: researcher-2001' \
  "$API/api/researcher/downloads/$TOKEN" | sed 's/^/   /'

say "7. 撤回后再发起导出 → CP-1 拦截"
curl -sS -w "\n   HTTP %{http_code}\n" -X POST "$API/api/researcher/projects/$RID/exports" \
  -H 'X-Test-Identity: researcher-2001' | sed 's/^/   /'

say "8. 历史访问记录保留可审计（最近 8 条，只追加）"
curl -sS "$API/api/events?limit=8" -H 'X-Test-Identity: admin-3001' \
  | $PY -c "
import sys,json
for e in json.load(sys.stdin):
    print('   %s  %-18s %s'%(e['occurred_at'][11:19], e['action'], e['detail']))"

echo
echo "浏览器演示：http://127.0.0.1:3000 （右上角切换参与者/研究员/管理员身份）"
