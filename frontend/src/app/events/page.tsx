"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useIdentity } from "@/components/IdentityProvider";
import { Alert, fmtTime } from "@/components/ui";

const LABEL: Record<string, string> = {
  request_submitted: "提交申请",
  request_approved: "批准申请（限时窗口）",
  request_rejected: "拒绝申请",
  export_queued: "导出入队",
  export_started: "worker 拾取任务",
  export_completed: "导出完成（已签发链接）",
  export_cancelled: "导出取消",
  download: "成功下载",
  download_denied: "下载被拒绝",
  link_revoked: "链接撤销",
  consent_granted: "授予授权",
  consent_withdrawn: "撤回授权",
};

const KIND: Record<string, string> = {
  request_submitted: "neutral",
  request_approved: "granted",
  request_rejected: "withdrawn",
  export_queued: "queued",
  export_started: "queued",
  export_completed: "complete",
  export_cancelled: "cancelled",
  download: "granted",
  download_denied: "withdrawn",
  link_revoked: "withdrawn",
  consent_granted: "granted",
  consent_withdrawn: "withdrawn",
};

export default function EventsPage() {
  const { me } = useIdentity();
  const [events, setEvents] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiFetch("/api/events?limit=100")
      .then(setEvents)
      .catch((e) => setErr(e.message));
  }, []);

  if (!me) return <Alert kind="info">请先选择身份。</Alert>;

  return (
    <div className="panel">
      <h2>访问事件（只追加审计流）</h2>
      <p className="desc">
        撤回不会删除或改写这里的任何记录；导出取消、链接撤销、下载拒绝都会留下带检查点标记的事件。
        {me.role === "admin" ? "当前为管理员视角：全部事件。" : "当前为个人视角：仅显示与你相关的事件。"}
      </p>
      {err && <Alert kind="err">{err}</Alert>}
      <table>
        <thead>
          <tr><th>时间</th><th>操作者</th><th>动作</th><th>关联</th><th>详情</th></tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td className="small whitespace-nowrap">{fmtTime(e.occurred_at)}</td>
              <td className="small">{e.actor_label || <span className="muted">系统（worker）</span>}</td>
              <td><span className={`badge ${KIND[e.action] || "neutral"}`}>{LABEL[e.action] || e.action}</span></td>
              <td className="small muted">
                {e.request_id && <>申请 #{e.request_id}<br /></>}
                {e.export_id && <>导出 #{e.export_id}<br /></>}
                {e.consent_id && <>授权 #{e.consent_id}</>}
              </td>
              <td className="mono small" style={{ maxWidth: 360 }}>
                {JSON.stringify(e.detail)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
