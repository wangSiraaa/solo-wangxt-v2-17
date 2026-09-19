"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useIdentity } from "@/components/IdentityProvider";
import { Alert, Badge, fmtTime } from "@/components/ui";

export default function AdminPage() {
  const { me } = useIdentity();
  const [tab, setTab] = useState<"requests" | "jobs">("requests");
  const [requests, setRequests] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load() {
    try {
      if (tab === "requests") setRequests(await apiFetch("/api/admin/requests"));
      else setJobs(await apiFetch("/api/admin/jobs"));
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(() => tab === "jobs" && load(), 3000);
    return () => clearInterval(t);
  }, [tab]);

  async function decide(id: number, approve: boolean) {
    setBusyId(id);
    setErr("");
    const minutesInput =
      typeof window !== "undefined"
        ? window.prompt(approve ? "授予限时下载窗口（分钟，默认 30）" : "拒绝理由（可留空）", approve ? "30" : "")
        : null;
    if (minutesInput === null) {
      setBusyId(null);
      return;
    }
    try {
      await apiFetch(`/api/admin/requests/${id}/decision`, {
        method: "POST",
        body: approve
          ? { approve: true, grant_minutes: Number(minutesInput) || 30, reviewer_note: "按用途批准" }
          : { approve: false, reviewer_note: minutesInput },
      });
      load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusyId(null);
    }
  }

  if (me?.role !== "admin") return <Alert kind="info">请切换到数据管理员身份。</Alert>;

  return (
    <div>
      <div className="panel">
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>数据管理员工作台</h2>
          <button className={`small ghost ${tab === "requests" ? "" : ""}`} onClick={() => setTab("requests")}>
            访问申请审批
          </button>
          <button className="small ghost" onClick={() => setTab("jobs")}>导出队列监控</button>
        </div>
        <p className="desc">
          管理员只授予“数据集 × 用途”的<strong>限时下载窗口</strong>，不能代替参与者变更授权；
          窗口到期或参与者撤回都会使导出与下载被检查点拦截。
        </p>
        {err && <Alert kind="err">{err}</Alert>}

        {tab === "requests" && (
          <table>
            <thead>
              <tr><th>#</th><th>研究员</th><th>数据集 / 用途</th><th>说明</th><th>状态</th><th>窗口</th><th>操作</th></tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.researcher_name}<div className="mono muted small">{r.researcher_code}</div></td>
                  <td>{r.dataset_title}<div className="muted small">{r.purpose_title}</div></td>
                  <td className="small" style={{ maxWidth: 220 }}>{r.justification || "—"}</td>
                  <td><Badge status={r.status} /></td>
                  <td>
                    {r.grant_active
                      ? <><span className="badge active">有效</span><div className="small muted">至 {fmtTime(r.grant_expires_at)}</div></>
                      : <span className="muted small">{r.status === "approved" ? "已过期" : "—"}</span>}
                  </td>
                  <td>
                    {r.status === "pending" && (
                      <>
                        <button className="small" disabled={busyId === r.id} onClick={() => decide(r.id, true)}>批准（限时）</button>{" "}
                        <button className="small danger" disabled={busyId === r.id} onClick={() => decide(r.id, false)}>拒绝</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === "jobs" && (
          <table>
            <thead>
              <tr><th>任务</th><th>研究员</th><th>数据集 / 用途</th><th>状态</th><th>行数</th><th>入队 / 结束</th><th>拒绝原因</th></tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>#{j.id}<div className="mono muted small">request {j.request_id}</div></td>
                  <td>{j.researcher_code}</td>
                  <td>{j.dataset_code}<div className="muted small">{j.purpose_code}</div></td>
                  <td><Badge status={j.status} /></td>
                  <td>{j.record_count ?? "—"}</td>
                  <td className="small">{fmtTime(j.requested_at)}<br />{fmtTime(j.finished_at)}</td>
                  <td className="small">{j.denial_reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
