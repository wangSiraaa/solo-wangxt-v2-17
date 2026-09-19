"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PUBLIC_API } from "../lib/api";
import { reasonLabel } from "../lib/labels";
import { Dataset, Purpose } from "../lib/types";

async function post(as: string, path: string, body?: unknown) {
  const res = await fetch(`${PUBLIC_API}${path}`, {
    method: "POST",
    headers: { "X-User-Id": as, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function reasonsText(detail: any): string {
  const reasons: string[] = detail?.reasons ?? [];
  return reasons.map(reasonLabel).join("、") || "操作被拒绝";
}

export function ResetDemoButton() {
  const router = useRouter();
  const [msg, setMsg] = useState("");
  async function run() {
    setMsg("重置中…");
    await post("A-001", "/api/demo/reset");
    setMsg("已重置为初始样本数据");
    router.refresh();
  }
  return (
    <span>
      <button className="secondary" onClick={run}>重置演示数据</button>
      {msg && <span className="msg muted">{msg}</span>}
    </span>
  );
}

export function ApplyForm({
  as,
  datasets,
  purposes,
}: {
  as: string;
  datasets: Dataset[];
  purposes: Purpose[];
}) {
  const router = useRouter();
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? "");
  const [purposeCode, setPurposeCode] = useState(purposes[0]?.code ?? "");
  const [title, setTitle] = useState("");
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const { ok, data } = await post(as, "/api/requests", {
      dataset_id: datasetId,
      purpose_code: purposeCode,
      project_title: title || "未命名项目",
    });
    setMsg(ok ? `申请 #${data.id} 已提交，等待管理员审批` : `提交失败：${JSON.stringify(data)}`);
    setTitle("");
    router.refresh();
  }

  return (
    <form className="inline" onSubmit={submit}>
      <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
        {datasets.map((d) => (
          <option key={d.id} value={d.id}>{d.id} · {d.name}</option>
        ))}
      </select>
      <select value={purposeCode} onChange={(e) => setPurposeCode(e.target.value)}>
        {purposes.map((p) => (
          <option key={p.code} value={p.code}>{p.name}</option>
        ))}
      </select>
      <input
        placeholder="项目标题，如：高血压风险因素分析"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        size={32}
      />
      <button type="submit">提交申请</button>
      {msg && <span className="msg muted">{msg}</span>}
    </form>
  );
}

export function ApproveControls({ as, requestId }: { as: string; requestId: number }) {
  const router = useRouter();
  const [days, setDays] = useState(7);
  const [msg, setMsg] = useState("");

  async function approve() {
    const { ok, data } = await post(as, `/api/admin/requests/${requestId}/approve`, { days_valid: days });
    setMsg(ok ? `已批准，授权 #${data.grant_id}` : `失败：${JSON.stringify(data)}`);
    router.refresh();
  }
  async function deny() {
    const { ok } = await post(as, `/api/admin/requests/${requestId}/deny`, { note: "用途说明不足" });
    setMsg(ok ? "已拒绝" : "操作失败");
    router.refresh();
  }

  return (
    <span>
      <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
        <option value={1}>1 天</option>
        <option value={7}>7 天</option>
        <option value={30}>30 天</option>
      </select>{" "}
      <button onClick={approve}>批准</button>{" "}
      <button className="secondary" onClick={deny}>拒绝</button>
      {msg && <span className="msg muted">{msg}</span>}
    </span>
  );
}

export function QueueExportButton({ as, grantId }: { as: string; grantId: number }) {
  const router = useRouter();
  const [msg, setMsg] = useState("");
  const [isErr, setIsErr] = useState(false);

  async function run() {
    const { ok, data } = await post(as, "/api/exports", { grant_id: grantId });
    setIsErr(!ok);
    setMsg(ok ? `导出任务 #${data.id} 已排队` : `排队被拒绝：${reasonsText(data.detail)}`);
    router.refresh();
  }

  return (
    <span>
      <button onClick={run}>排队导出</button>
      {msg && <span className={`msg ${isErr ? "err-text" : "ok-text"}`}>{msg}</span>}
    </span>
  );
}

export function RunWorkerButton({ as }: { as: string }) {
  const router = useRouter();
  const [msg, setMsg] = useState("");

  async function run() {
    setMsg("执行中…");
    const { data } = await post(as, "/api/admin/worker/run");
    const items: { id: number; status: string }[] = data.processed ?? [];
    setMsg(
      items.length === 0
        ? "没有待执行的导出任务"
        : items.map((i) => `任务 #${i.id} → ${i.status}`).join("；")
    );
    router.refresh();
  }

  return (
    <span>
      <button onClick={run}>立即执行导出队列</button>
      {msg && <span className="msg muted">{msg}</span>}
    </span>
  );
}

export function ConsentButton({
  as,
  purposeCode,
  action,
}: {
  as: string;
  purposeCode: string;
  action: "grant" | "withdraw";
}) {
  const router = useRouter();
  const [msg, setMsg] = useState("");

  async function run() {
    const { data } = await post(as, `/api/participants/me/consents/${purposeCode}`, { action });
    if (action === "withdraw") {
      const n = data.cancelled_exports?.length ?? 0;
      setMsg(
        n > 0
          ? `已撤回（版本 v${data.version}），${n} 个排队导出被取消`
          : `已撤回（版本 v${data.version}），当前无排队导出受影响`
      );
    } else {
      setMsg(`已重新授权（版本 v${data.version}）`);
    }
    router.refresh();
  }

  const cls = action === "withdraw" ? "danger" : "";
  return (
    <span>
      <button className={cls} onClick={run}>
        {action === "withdraw" ? "撤回授权" : "重新授权"}
      </button>
      {msg && <span className="msg muted">{msg}</span>}
    </span>
  );
}

export function LinkChecker({ token }: { token: string }) {
  const [msg, setMsg] = useState("");
  const [valid, setValid] = useState<boolean | null>(null);

  async function check() {
    const res = await fetch(`${PUBLIC_API}/api/downloads/${token}/check`);
    const data = await res.json();
    setValid(data.valid);
    setMsg(
      data.valid
        ? "链接当前有效"
        : `链接已失效：${(data.reasons ?? []).map(reasonLabel).join("、")}` +
            (data.withdrawn_participants?.length
              ? `（撤回者：${data.withdrawn_participants.join("、")}）`
              : "")
    );
  }

  return (
    <span>
      <button className="secondary" onClick={check}>校验链接</button>
      {msg && (
        <span className={`msg ${valid ? "ok-text" : "err-text"}`}>{msg}</span>
      )}
    </span>
  );
}
