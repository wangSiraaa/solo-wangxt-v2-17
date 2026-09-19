export function Badge({ status }: { status: string }) {
  const map: Record<string, string> = {
    granted: "已授予",
    withdrawn: "已撤回",
    approved: "已批准",
    rejected: "已拒绝",
    pending: "待审批",
    queued: "排队中",
    running: "生成中",
    cancelled: "已取消",
    complete: "已生成",
    complete_unused: "已生成·未下载",
    downloaded: "已下载",
    active: "窗口有效",
    expired: "窗口过期",
  };
  return <span className={`badge ${status}`}>{map[status] || status}</span>;
}

export function JobBadge({ job }: { job: any }) {
  if (job.status === "complete") {
    const used = Number(job.links_used || 0) > 0;
    return (
      <span className={`badge ${used ? "downloaded" : "complete"}`}>
        {used ? "已生成·已下载" : "已生成·尚未下载"}
      </span>
    );
  }
  return <Badge status={job.status} />;
}

export function fmtTime(t: string | null) {
  if (!t) return "—";
  const d = new Date(t);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function Alert({ kind, children }: { kind: "ok" | "err" | "info"; children: React.ReactNode }) {
  return <div className={`alert ${kind}`}>{children}</div>;
}
