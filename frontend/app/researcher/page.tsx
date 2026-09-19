import Link from "next/link";
import PersonaNav from "../components/PersonaNav";
import Badge from "../components/Badge";
import { apiGet, PUBLIC_API } from "../lib/api";
import {
  EXPORT_STATUS,
  REQUEST_STATUS,
  fmtTime,
  reasonLabel,
} from "../lib/labels";
import {
  AccessRequest,
  Dataset,
  ExportInfo,
  Purpose,
} from "../lib/types";
import { ApplyForm, LinkChecker, QueueExportButton } from "../components/widgets";

const RESEARCHERS = ["R-101", "R-102"];

export default async function ResearcherPage({
  searchParams,
}: {
  searchParams: { as?: string };
}) {
  const as = searchParams.as ?? "R-101";
  const catalog = await apiGet<{ datasets: Dataset[]; purposes: Purpose[] }>(
    "/api/datasets",
    as
  );
  const { requests } = await apiGet<{ requests: AccessRequest[] }>(
    "/api/requests/mine",
    as
  );
  const { exports } = await apiGet<{ exports: ExportInfo[] }>(
    "/api/exports/mine",
    as
  );

  return (
    <>
      <PersonaNav as={as} />
      <div className="persona-switch">
        <span className="muted small">切换研究员：</span>
        {RESEARCHERS.map((id) => (
          <Link key={id} href={`/researcher?as=${id}`} className={id === as ? "active" : ""}>
            {id}
          </Link>
        ))}
      </div>

      <div className="card">
        <h2>数据集目录</h2>
        <p className="sub">选择数据集与用途，提交访问申请</p>
        <table>
          <thead>
            <tr><th>数据集</th><th>名称</th><th>记录数</th><th>参与者数</th><th>说明</th></tr>
          </thead>
          <tbody>
            {catalog.datasets.map((d) => (
              <tr key={d.id}>
                <td className="mono">{d.id}</td>
                <td>{d.name}</td>
                <td>{d.record_count}</td>
                <td>{d.participant_count}</td>
                <td className="muted small">{d.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ marginTop: 12 }}>
          <ApplyForm as={as} datasets={catalog.datasets} purposes={catalog.purposes} />
        </div>
      </div>

      <div className="card">
        <h2>我的申请</h2>
        <p className="sub">管理员批准后获得限时下载权限，可排队导出</p>
        {requests.length === 0 ? (
          <p className="muted">还没有申请记录。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th><th>项目</th><th>数据集</th><th>用途</th>
                <th>状态</th><th>授权有效期至</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id}</td>
                  <td>{r.project_title}</td>
                  <td className="mono">{r.dataset_id}</td>
                  <td>{r.purpose_code}</td>
                  <td>
                    <Badge
                      label={REQUEST_STATUS[r.status].label}
                      cls={REQUEST_STATUS[r.status].cls}
                    />
                    {r.decision_note && (
                      <div className="small muted">{r.decision_note}</div>
                    )}
                  </td>
                  <td className="small">{r.grant ? fmtTime(r.grant.expires_at) : "—"}</td>
                  <td>
                    {r.grant && <QueueExportButton as={as} grantId={r.grant.id} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>我的导出</h2>
        <p className="sub">
          "已下载"表示链接至少成功访问过一次；"未下载"的链接仍可下载——除非授权被撤回
        </p>
        {exports.length === 0 ? (
          <p className="muted">还没有导出任务。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th><th>数据集</th><th>用途</th><th>状态</th><th>行数</th>
                <th>下载状态</th><th>下载链接</th>
              </tr>
            </thead>
            <tbody>
              {exports.map((e) => (
                <tr key={e.id}>
                  <td className="mono">{e.id}</td>
                  <td className="mono">{e.dataset_id}</td>
                  <td>{e.purpose_code}</td>
                  <td>
                    <Badge
                      label={EXPORT_STATUS[e.status].label}
                      cls={EXPORT_STATUS[e.status].cls}
                    />
                    {e.cancel_reason && (
                      <div className="small err-text">
                        {e.cancel_reason.split(",").map(reasonLabel).join("、")}
                      </div>
                    )}
                  </td>
                  <td>{e.row_count ?? "—"}</td>
                  <td>
                    {e.status === "completed" ? (
                      e.downloaded ? (
                        <Badge label="已下载" cls="badge-gray" />
                      ) : (
                        <Badge label="未下载" cls="badge-amber" />
                      )
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {e.download_token ? (
                      <span>
                        <a
                          className="btn secondary"
                          href={`${PUBLIC_API}/api/downloads/${e.download_token}`}
                        >
                          下载 CSV
                        </a>{" "}
                        <LinkChecker token={e.download_token} />
                        <div className="small muted">
                          链接有效期至 {fmtTime(e.link_expires_at)}
                        </div>
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
