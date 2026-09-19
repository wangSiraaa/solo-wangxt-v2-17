"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useIdentity } from "@/components/IdentityProvider";
import { Alert, Badge, fmtTime } from "@/components/ui";

const ACTION_LABEL: Record<string, string> = {
  granted: "授予",
  withdrawn: "撤回",
};

export default function ParticipantPage() {
  const { me } = useIdentity();
  const [consents, setConsents] = useState<any[]>([]);
  const [affected, setAffected] = useState<Record<number, any[]>>({});
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [confirmPurpose, setConfirmPurpose] = useState<any | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const cs = await apiFetch<any[]>("/api/participant/consents");
      setConsents(cs);
      const af: Record<number, any[]> = {};
      await Promise.all(
        cs.map(async (c) => {
          af[c.purpose_id] = await apiFetch(
            `/api/participant/affected-projects?purpose_id=${c.purpose_id}`
          );
        })
      );
      setAffected(af);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function doWithdraw() {
    if (!confirmPurpose) return;
    setBusy(true);
    setErr("");
    try {
      const r = await apiFetch("/api/participant/consents/withdraw", {
        method: "POST",
        body: { purpose_id: confirmPurpose.purpose_id, reason },
      });
      setOk(
        `已撤回「${confirmPurpose.purpose_title}」（版本 v${r.version}）：` +
          `${r.cancelled_export_ids.length} 个未完成导出已取消，` +
          `${r.revoked_link_ids.length} 个下载链接已撤销；历史访问记录保留。`
      );
      setConfirmPurpose(null);
      setReason("");
      load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function regrant(purposeId: number) {
    setErr("");
    try {
      await apiFetch("/api/participant/consents/regrant", {
        method: "POST",
        body: { purpose_id: purposeId },
      });
      setOk("已重新授予授权（新版本）；此前已取消的任务与已撤销链接不会自动恢复，需研究员重新发起导出。");
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  if (me?.role !== "participant") return <Alert kind="info">请切换到参与者身份（独立撤回入口）。</Alert>;

  return (
    <div>
      <div className="panel">
        <h2>我的数据授权</h2>
        <p className="desc">
          独立于研究员和管理员的参与者入口。撤回按<strong>用途</strong>生效：
          未完成的导出将被取消，已发放的下载链接将失效并在再次访问时重新校验；
          已发生的访问与下载历史不会被删除。
        </p>
        {ok && <Alert kind="ok">{ok}</Alert>}
        {err && <Alert kind="err">{err}</Alert>}

        {consents.map((c) => {
          const projects = affected[c.purpose_id] || [];
          return (
            <div key={c.consent_id} className="panel" style={{ background: "#fbfdff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <strong>{c.purpose_title}</strong>{" "}
                  <Badge status={c.status} />
                  <span className="muted small"> 当前版本 v{c.version}</span>
                </div>
                <div>
                  {c.status === "granted" ? (
                    <button className="small danger" onClick={() => { setOk(""); setConfirmPurpose(c); }}>
                      撤回此用途授权
                    </button>
                  ) : (
                    <button className="small" onClick={() => regrant(c.purpose_id)}>重新授予</button>
                  )}
                </div>
              </div>
              <p className="small muted" style={{ margin: "8px 0 4px" }}>{c.purpose_description}</p>
              {c.status === "withdrawn" && (
                <p className="small" style={{ color: "var(--red)", margin: "4px 0" }}>
                  撤回于 {fmtTime(c.withdrawn_at)}，理由：{c.withdraw_reason || "（未填写）"}
                </p>
              )}

              <div className="grid2" style={{ marginTop: 8 }}>
                <div>
                  <h3 style={{ marginTop: 4 }}>授权版本历史</h3>
                  <ul className="timeline">
                    {c.history.map((h: any, idx: number) => (
                      <li key={idx} className={h.action}>
                        <span className={`badge ${h.action}`} style={{ marginRight: 6 }}>
                          v{h.version} {ACTION_LABEL[h.action]}
                        </span>
                        {fmtTime(h.occurred_at)}
                        {h.reason && <div className="muted">{h.reason}</div>}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 style={{ marginTop: 4 }}>将受影响 / 已受影响的研究项目（{projects.length}）</h3>
                  {projects.length === 0 ? (
                    <div className="small muted">目前没有研究员申请使用含本人记录的该数据集。</div>
                  ) : (
                    <table>
                      <thead><tr><th>项目</th><th>状态</th><th>导出任务</th></tr></thead>
                      <tbody>
                        {projects.map((p) => (
                          <tr key={p.request_id}>
                            <td className="small">
                              #{p.request_id} {p.researcher_name}
                              <div className="muted">{p.dataset_code}</div>
                            </td>
                            <td>
                              <Badge status={p.request_status} />
                              {p.grant_active && <div className="badge active small" style={{ marginTop: 4 }}>窗口有效</div>}
                            </td>
                            <td className="small">
                              <span className="badge queued">{p.pending_count} 排队</span>{" "}
                              <span className="badge complete">{p.complete_count} 已生成</span>{" "}
                              <span className="badge cancelled">{p.cancelled_count} 已取消</span>
                              {p.jobs?.filter((j: any) => j.status === "complete").map((j: any) => (
                                <div key={j.id} className="small muted" style={{ marginTop: 2 }}>
                                  任务#{j.id}：{j.links_used > 0 ? "曾被下载（历史保留）" : "尚未下载"}
                                  {j.links_revoked > 0 ? "，链接已撤销" : ""}
                                </div>
                              ))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {confirmPurpose && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15,23,42,.45)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50,
        }} onClick={() => setConfirmPurpose(null)}>
          <div className="panel" style={{ maxWidth: 520, width: "92%", margin: 0 }} onClick={(e) => e.stopPropagation()}>
            <h2>确认撤回：{confirmPurpose.purpose_title}</h2>
            <p className="desc">撤回将立即产生以下效果：</p>
            <ul className="small" style={{ paddingLeft: 18, lineHeight: 1.9 }}>
              <li>所有<strong>排队中 / 生成中</strong>的相关导出任务被取消（<span className="checkpoint">CP-3</span>），不产出文件；</li>
              <li>已生成导出的<strong>下载链接被撤销</strong>，研究员再次访问会被 <span className="checkpoint">CP-4</span> 拒绝；</li>
              <li>历史访问与下载事件保留可审计，不做删除；</li>
              <li>撤回以新版本记录（当前 v{confirmPurpose.version} → v{confirmPurpose.version + 1}）。</li>
            </ul>
            <div className="small muted">
              受影响项目：{(affected[confirmPurpose.purpose_id] || []).length} 个
              {" · "}
              排队/生成中任务：
              {(affected[confirmPurpose.purpose_id] || []).reduce(
                (s: number, p: any) => s + p.pending_count, 0)}
              个
            </div>
            <label>撤回理由（可选，将写入版本历史）</label>
            <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="例如：不再希望本人数据用于该类研究" />
            <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
              <button className="danger" disabled={busy} onClick={doWithdraw}>
                {busy ? "处理中…" : "确认撤回"}
              </button>
              <button className="ghost" onClick={() => setConfirmPurpose(null)}>取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
