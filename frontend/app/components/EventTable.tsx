import { AccessEvent } from "../lib/types";
import { EVENT_LABELS, fmtTime } from "../lib/labels";

export default function EventTable({ events }: { events: AccessEvent[] }) {
  if (events.length === 0) {
    return <p className="muted">暂无事件。</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>事件</th>
          <th>操作者</th>
          <th>用途</th>
          <th>数据集</th>
          <th>导出</th>
          <th>详情</th>
          <th>时间</th>
        </tr>
      </thead>
      <tbody>
        {events.map((ev) => (
          <tr key={ev.id}>
            <td className="mono">{ev.id}</td>
            <td>{EVENT_LABELS[ev.event_type] ?? ev.event_type}</td>
            <td className="mono">{ev.actor_id}</td>
            <td>{ev.purpose_code ?? "—"}</td>
            <td>{ev.dataset_id ?? "—"}</td>
            <td>{ev.export_job_id ? `#${ev.export_job_id}` : "—"}</td>
            <td className="small muted">
              {ev.detail ? JSON.stringify(ev.detail) : "—"}
            </td>
            <td className="small">{fmtTime(ev.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
