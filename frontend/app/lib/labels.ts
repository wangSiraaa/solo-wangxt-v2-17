export const EVENT_LABELS: Record<string, string> = {
  request_submitted: "申请提交",
  request_approved: "批准申请 · 发放授权",
  request_denied: "拒绝申请",
  export_queued: "导出排队",
  export_started: "导出开始执行",
  export_completed: "导出完成",
  export_cancelled: "导出被取消",
  download_issued: "下载链接签发",
  download_served: "下载成功",
  download_denied: "下载被拒绝",
  consent_granted: "授予授权",
  consent_withdrawn: "撤回授权",
};

export const EXPORT_STATUS: Record<string, { label: string; cls: string }> = {
  queued: { label: "排队中", cls: "badge-blue" },
  running: { label: "执行中", cls: "badge-blue" },
  completed: { label: "已完成", cls: "badge-green" },
  cancelled: { label: "已取消", cls: "badge-red" },
  failed: { label: "失败", cls: "badge-red" },
};

export const REQUEST_STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: "待审批", cls: "badge-amber" },
  approved: { label: "已批准", cls: "badge-green" },
  denied: { label: "已拒绝", cls: "badge-red" },
};

export const CONSENT_STATUS: Record<string, { label: string; cls: string }> = {
  granted: { label: "已授权", cls: "badge-green" },
  withdrawn: { label: "已撤回", cls: "badge-red" },
  none: { label: "从未授权", cls: "badge-gray" },
};

export const REASON_LABELS: Record<string, string> = {
  consent_withdrawn: "参与者已撤回授权",
  grant_expired: "授权已过期",
  link_expired: "下载链接已过期",
  export_not_completed: "导出尚未完成",
};

export const PURPOSE_NAMES: Record<string, string> = {
  cardio: "心血管研究",
  diabetes: "糖尿病研究",
  genomics: "基因组分析",
};

export function reasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").toLocaleString("zh-CN", { hour12: false });
}
