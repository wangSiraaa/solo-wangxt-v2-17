import Link from "next/link";
import PersonaNav from "../components/PersonaNav";
import Badge from "../components/Badge";
import EventTable from "../components/EventTable";
import { apiGet } from "../lib/api";
import { CONSENT_STATUS, EXPORT_STATUS, fmtTime } from "../lib/labels";
import { AccessEvent, PurposeOverview } from "../lib/types";
import { ConsentButton } from "../components/widgets";

const PARTICIPANTS = Array.from({ length: 10 }, (_, i) => `P-${String(i + 1).padStart(3, "0")}`);

export default async function ParticipantPage({
  searchParams,
}: {
  searchParams: { as?: string };
}) {
  const as = searchParams.as ?? "P-001";
  const overview = await apiGet<{
    participant_id: string;
    label: string;
    purposes: PurposeOverview[];
  }>("/api/participants/me/overview", as);
  const { events } = await apiGet<{ events: AccessEvent[] }>(
    "/api/participants/me/events?limit=50",
    as
  );

  return (
    <>
      <PersonaNav as={as} />
      <div className="persona-switch">
        <span className="muted small">切换参与者：</span>
        {PARTICIPANTS.map((id) => (
          <Link key={id} href={`/participant?as=${id}`} className={id === as ? "active" : ""}>
            {id}
          </Link>
        ))}
      </div>

      <div className="card">
        <h2>
          我的授权 <span className="muted small">（{overview.label} · {overview.participant_id}）</span>
        </h2>
        <p className="sub">
          按用途独立授权。撤回后：排队中的导出立即取消、执行中的导出在提交前被拦截、已发放的下载链接再次访问时失效；历史访问记录保留不变。
        </p>
      </div>

      {overview.purposes.map((p) => {
        const st = CONSENT_STATUS[p.status];
        const impact = p.withdrawal_impact;
        return (
          <div className="card" key={p.code}>
            <h3>
              {p.name} <span className="mono muted small">({p.code})</span>{" "}
              <Badge label={st.label} cls={st.cls} />{" "}
              <span className="muted small">版本 v{p.version}</span>
            </h3>
            <p className="sub">{p.description} · 涉及数据集：{p.datasets.join("、") || "无"}</p>
            {p.status === "granted" ? (
              <ConsentButton as={as} purposeCode={p.code} action="withdraw" />
            ) : (
              <ConsentButton as={as} purposeCode={p.code} action="grant" />
            )}
            {p.status === "granted" &&
              (impact.queued_exports > 0 || impact.active_download_links > 0) && (
                <div className="warn-box">
                  若现在撤回：{impact.queued_exports} 个排队中的导出将被取消，
                  {impact.active_download_links} 个已发放的下载链接将失效。
                </div>
              )}

            {p.projects.length > 0 && (
              <>
                <h3 style={{ marginTop: 14 }}>受影响项目（{p.projects.length}）</h3>
                <table>
                  <thead>
                    <tr>
                      <th>项目</th><th>研究员</th><th>数据集</th>
                      <th>授权有效期至</th><th>导出任务</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.projects.map((proj) => (
                      <tr key={proj.grant_id}>
                        <td>{proj.project_title}</td>
                        <td>{proj.researcher_name}</td>
                        <td className="mono">{proj.dataset_id}</td>
                        <td className="small">{fmtTime(proj.grant_expires_at)}</td>
                        <td>
                          {proj.exports.length === 0
                            ? "—"
                            : proj.exports.map((e) => (
                                <span key={e.id} style={{ marginRight: 8 }}>
                                  #{e.id}{" "}
                                  <Badge
                                    label={EXPORT_STATUS[e.status]?.label ?? e.status}
                                    cls={EXPORT_STATUS[e.status]?.cls ?? "badge-gray"}
                                  />
                                  {e.status === "completed" && (
                                    <span className="small muted">
                                      {e.downloaded ? "已下载" : "未下载"}
                                    </span>
                                  )}
                                </span>
                              ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        );
      })}

      <div className="card">
        <h2>我的数据访问历史</h2>
        <p className="sub">涉及我的数据的所有事件，包括撤回前的历史访问——这些记录不会被删除</p>
        <EventTable events={events} />
      </div>
    </>
  );
}
