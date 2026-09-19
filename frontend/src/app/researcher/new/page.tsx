"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useIdentity } from "@/components/IdentityProvider";
import { Alert } from "@/components/ui";

export default function NewRequest() {
  const { me } = useIdentity();
  const router = useRouter();
  const [catalog, setCatalog] = useState<any>(null);
  const [datasetId, setDatasetId] = useState<number>(1);
  const [purposeId, setPurposeId] = useState<number>(1);
  const [justification, setJustification] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch("/api/catalog").then(setCatalog).catch((e) => setErr(e.message));
  }, []);

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const r = await apiFetch("/api/researcher/requests", {
        method: "POST",
        body: { dataset_id: datasetId, purpose_id: purposeId, justification },
      });
      router.push(`/researcher/projects/${r.id}`);
    } catch (e: any) {
      setErr(e.message);
      setBusy(false);
    }
  }

  if (me?.role !== "researcher") return <Alert kind="info">请切换到研究员身份。</Alert>;

  return (
    <div className="panel" style={{ maxWidth: 640 }}>
      <h2>新建数据集访问申请</h2>
      <p className="desc">授权按“用途”授予与撤回：请明确数据使用目的，管理员将按用途批准限时下载窗口。</p>
      {err && <Alert kind="err">{err}</Alert>}

      <label>脱敏数据集</label>
      <select value={datasetId} onChange={(e) => setDatasetId(Number(e.target.value))}>
        {catalog?.datasets.map((d: any) => (
          <option key={d.id} value={d.id}>
            {d.title}（{d.record_count} 行 / {d.participant_count} 名参与者，已脱敏）
          </option>
        ))}
      </select>
      {catalog?.datasets?.[0] && (
        <p className="small muted" style={{ marginTop: 6 }}>{catalog.datasets[0].description}</p>
      )}

      <label>数据用途</label>
      <select value={purposeId} onChange={(e) => setPurposeId(Number(e.target.value))}>
        {catalog?.purposes.map((p: any) => {
          const cov = catalog.coverage.find((c: any) => c.purpose_id === p.id);
          return (
            <option key={p.id} value={p.id}>
              {p.title}（当前 {cov?.granted_count}/{cov?.total_count} 名参与者授权）
            </option>
          );
        })}
      </select>
      <p className="small muted" style={{ marginTop: 6 }}>
        {catalog?.purposes?.find((p: any) => p.id === purposeId)?.description}
      </p>

      <label>用途说明（研究方案摘要）</label>
      <textarea rows={4} value={justification} onChange={(e) => setJustification(e.target.value)}
        placeholder="例如：用于糖尿病风险因素的逻辑回归建模，仅在机构环境内聚合分析……" />

      <div style={{ marginTop: 16 }}>
        <button onClick={submit} disabled={busy}>{busy ? "提交中…" : "提交申请"}</button>
      </div>
    </div>
  );
}
