import PersonaNav from "../components/PersonaNav";
import Badge from "../components/Badge";
import EventTable from "../components/EventTable";
import { apiGet } from "../lib/api";
import { REQUEST_STATUS, fmtTime } from "../lib/labels";
import { AccessEvent, AccessRequest } from "../lib/types";
import { ApproveControls, RunWorkerButton } from "../components/widgets";

export default async function AdminPage({
  searchParams,
}: {
  searchParams: { as?: string };
}) {
  const as = searchParams.as ?? "A-001";
  const { requests } = await apiGet<{ requests: AccessRequest[] }>(
    "/api/admin/requests",
    as
  );
  const { events } = await apiGet<{ events: AccessEvent[] }>(
    "/api/admin/events?limit=50",
    as
  );
  const pending = requests.filter((r) => r.status === "pending");
  const decided = requests.filter((r) => r.status !== "pending");

  return (
    <>
      <PersonaNav as={as} />

      <div className="card">
        <h2>待审批申请</h2>
        <p className="sub">按用途发放限时下载权限（1 / 7 / 30 天）</p>
        {pending.length === 0 ? (
          <p className="muted">没有待审批的申请。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th><th>研究员</th><th>项目</th><th>数据集</th>
                <th>用途</th><th>申请时间</th><th>审批</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id}</td>
                  <td>{r.researcher_name}</td>
                  <td>{r.project_title}</td>
                  <td className="mono">{r.dataset_id}</td>
                  <td>{r.purpose_code}</td>
                  <td className="small">{fmtTime(r.created_at)}</td>
                  <td><ApproveControls as={as} requestId={r.id} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>导出队列</h2>
        <p className="sub">
          Worker 执行导出前与提交前各做一次权限校验；撤回发生在执行窗口内时，任务会在提交前检查点被取消
        </p>
        <RunWorkerButton as={as} />
      </div>

      <div className="card">
        <h2>全部申请</h2>
        {decided.length === 0 ? (
          <p className="muted">暂无已处理的申请。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th><th>研究员</th><th>项目</th><th>数据集</th>
                <th>用途</th><th>状态</th><th>授权有效期至</th>
              </tr>
            </thead>
            <tbody>
              {decided.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id}</td>
                  <td>{r.researcher_name}</td>
                  <td>{r.project_title}</td>
                  <td className="mono">{r.dataset_id}</td>
                  <td>{r.purpose_code}</td>
                  <td>
                    <Badge
                      label={REQUEST_STATUS[r.status].label}
                      cls={REQUEST_STATUS[r.status].cls}
                    />
                  </td>
                  <td className="small">{r.grant ? fmtTime(r.grant.expires_at) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>审计事件流</h2>
        <p className="sub">不可变日志：撤回不会删除历史访问记录，成功与拒绝的访问都留痕</p>
        <EventTable events={events} />
      </div>
    </>
  );
}
