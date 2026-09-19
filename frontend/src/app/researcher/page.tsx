"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { useIdentity } from "@/components/IdentityProvider";
import { Alert, Badge, fmtTime } from "@/components/ui";

export default function ResearcherHome() {
  const { me } = useIdentity();
  const [projects, setProjects] = useState<any[]>([]);
  const [err, setErr] = useState("");

  async function load() {
    try {
      setProjects(await apiFetch("/api/researcher/projects"));
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 3000); // 轮询导出状态
    return () => clearInterval(t);
  }, []);

  if (me?.role !== "researcher") return <Alert kind="info">请切换到研究员身份。</Alert>;

  return (
    <div>
      <div className="panel">
        <h2>我的研究项目</h2>
        <p className="desc">
          每个项目 = 一个“数据集 × 用途”的申请。批准后获得限时下载窗口；
          导出任务区分<strong>已下载</strong>与<strong>尚未下载</strong>；参与者撤回后，
          未完成任务被取消、已发链接失效。
        </p>
        {err && <Alert kind="err">{err}</Alert>}
        <div style={{ marginBottom: 12 }}>
          <Link href="/researcher/new"><button className="small">+ 新建数据集访问申请</button></Link>
        </div>
        {projects.length === 0 ? (
          <div className="muted small">还没有申请，点击上方按钮新建。</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th><th>数据集</th><th>用途</th><th>申请状态</th><th>下载窗口</th>
                <th>导出任务（排队/已生成/已取消）</th><th></th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{p.dataset_title}<div className="mono muted small">{p.dataset_code}</div></td>
                  <td>{p.purpose_title}</td>
                  <td><Badge status={p.status} /></td>
                  <td>
                    {p.grant_active ? (
                      <>
                        <Badge status="active" />
                        <div className="small muted">至 {fmtTime(p.grant_expires_at)}</div>
                      </>
                    ) : p.status === "approved" ? (
                      <Badge status="expired" />
                    ) : (
                      <span className="muted small">—</span>
                    )}
                  </td>
                  <td>
                    <span className="badge queued">{p.pending_count} 排队中</span>{" "}
                    <span className="badge complete">{p.complete_count} 已生成</span>{" "}
                    <span className="badge cancelled">{p.cancelled_count} 已取消</span>
                  </td>
                  <td><Link href={`/researcher/projects/${p.id}`}><button className="small ghost">查看</button></Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
