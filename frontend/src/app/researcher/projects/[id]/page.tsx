"use client";

import { use, useEffect, useRef, useState } from "react";
import { apiFetch, downloadAsBlob } from "@/lib/api";
import { useIdentity } from "@/components/IdentityProvider";
import { Alert, JobBadge, fmtTime } from "@/components/ui";

export default function ProjectDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { me } = useIdentity();
  const [project, setProject] = useState<any>(null);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");
  const [downloading, setDownloading] = useState<number | null>(null);
  const errRef = useRef("");

  async function load(silent = true) {
    try {
      const d = await apiFetch(`/api/researcher/projects/${id}`);
      setProject(d);
      errRef.current = "";
    } catch (e: any) {
      errRef.current = e.message;
      setErr(e.message);
    }
  }

  useEffect(() => {
    load(false);
  }, [id]);

  // 只要存在 queued/running 任务就持续轮询
  useEffect(() => {
    const pending = project?.jobs?.some((j: any) => ["queued", "running"].includes(j.status));
    if (!pending) return;
    const t = setInterval(() => load(true), 1500);
    return () => clearInterval(t);
  }, [project]);

  async function queueExport() {
    setErr("");
    setNotice("");
    try {
      await apiFetch(`/api/researcher/projects/${id}/exports`, { method: "POST" });
      setNotice("导出已入队（CP-1 检查通过），等待 worker 生成…");
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function download(jobId: number, token: string) {
    setDownloading(jobId);
    setErr("");
    try {
      const { blob, filename } = await downloadAsBlob(`/api/researcher/downloads/${token}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setNotice(`文件 ${filename} 已下载（本次访问通过 CP-4 实时授权校验）。`);
      load();
    } catch (e: any) {
      setErr(`下载被拒绝：${e.message}`);
      load(); // 刷新链接状态（可能已撤销）
    } finally {
      setDownloading(null);
    }
  }

  if (me?.role !== "researcher") return <Alert kind="info">请切换到研究员身份。</Alert>;
  if (!project && !err) return <div className="muted">加载中…</div>;
  if (!project) return <Alert kind="err">{err}</Alert>;

  return (
    <div>
      <div className="panel">
        <h2>项目 #{project.id}：{project.dataset_title}</h2>
        <p className="desc">{project.dataset_code} · 用途：{project.purpose_title}</p>
        {notice && <Alert kind="ok">{notice}</Alert>}
        {err && <Alert kind="err">{err}</Alert>}

        <div className="kv">
          <div className="k">申请状态</div><div><span className={`badge ${project.status}`}>
            {project.status === "approved" ? "已批准" : project.status === "rejected" ? "已拒绝" : "待审批"}
          </span></div>
          <div className="k">提交时间</div><div>{fmtTime(project.submitted_at)}</div>
          <div className="k">审批时间</div><div>{fmtTime(project.decided_at)}</div>
          <div className="k">下载窗口</div>
          <div>
            {project.grant_active
              ? <>有效，至 {fmtTime(project.grant_expires_at)}（限时授权）</>
              : project.status === "approved"
                ? <span className="badge expired">已过期</span>
                : "批准后开通"}
            {project.reviewer_note && <div className="small muted">管理员备注：{project.reviewer_note}</div>}
          </div>
          <div className="k">用途说明</div><div>{project.justification || "—"}</div>
        </div>

        <div style={{ marginTop: 14 }}>
          {project.status === "pending" && <Alert kind="info">申请正在等待管理员审批。</Alert>}
          {project.status === "rejected" && <Alert kind="err">申请被拒绝：{project.reviewer_note}</Alert>}
          {project.status === "approved" && (
            <button onClick={queueExport} disabled={!project.grant_active}>
              {project.grant_active ? "发起新导出（进入队列）" : "下载窗口已过期，需重新申请"}
            </button>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>导出任务与下载</h2>
        <p className="desc">
          排队中的任务尚未产出文件；参与者在其生成前撤回会取消任务。
          已生成任务区分<strong>尚未下载</strong>与<strong>已下载</strong>；
          已发链接每次访问都经过 <span className="checkpoint">CP-4</span> 实时授权校验。
        </p>
        {project.jobs.length === 0 && <div className="muted small">暂无导出任务。</div>}
        {project.jobs.map((job: any) => (
          <div key={job.id} className="panel" style={{ background: "#fbfdff" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <div>
                <strong>任务 #{job.id}</strong> <JobBadge job={job} />
                <div className="small muted" style={{ marginTop: 4 }}>
                  入队 {fmtTime(job.requested_at)}
                  {job.started_at && <> · 开始 {fmtTime(job.started_at)}</>}
                  {job.finished_at && <> · 结束 {fmtTime(job.finished_at)}</>}
                  {job.record_count != null && <> · {job.record_count} 行</>}
                </div>
              </div>
              <div>
                {job.status === "queued" && <span className="small muted">已入队，等待 worker…（<span className="spinner" />）</span>}
                {job.status === "running" && <span className="small muted">正在生成，写文件前有 <span className="checkpoint">CP-2</span> 授权检查点…（<span className="spinner" />）</span>}
                {job.status === "cancelled" && (
                  <span className="small" style={{ color: "var(--red)" }}>
                    未产出文件，原因：{job.denial_reason === "participant_withdrew"
                      ? "参与者已撤回授权"
                      : job.denial_reason === "grant_expired" ? "下载窗口过期" : job.denial_reason}
                  </span>
                )}
                {job.status === "complete" && (
                  job.active_token ? (
                    <button className="small" disabled={downloading === job.id}
                      onClick={() => download(job.id, job.active_token)}>
                      {downloading === job.id ? "校验中…" : "下载 CSV（实时校验授权）"}
                    </button>
                  ) : (
                    <span className="badge revoked">
                      链接已失效{job.links_revoked ? "（授权撤回后撤销）" : "（窗口过期）"}
                    </span>
                  )
                )}
              </div>
            </div>
            {job.status === "complete" && (
              <div className="small muted" style={{ marginTop: 6 }}>
                链接 {job.links_total} 个 · 已撤销 {job.links_revoked} 个 ·
                已下载次数 {job.links_used}
                {job.links_used > 0 ? "（历史下载事实保留，撤回不会删除）" : "（生成后尚未下载）"}
                {job.file_sha256 && <> · SHA256 <span className="mono">{job.file_sha256.slice(0, 16)}…</span></>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
