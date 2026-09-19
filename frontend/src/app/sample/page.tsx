"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Alert } from "@/components/ui";

export default function SamplePage() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [catalog, setCatalog] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiFetch("/api/catalog").then(setCatalog).catch((e) => setErr(e.message));
    apiFetch("/api/datasets/1/sample-records").then(setRows).catch((e) => setErr(e.message));
  }, []);

  const allKeys = Array.from(
    new Set((rows || []).flatMap((r) => Object.keys(r.payload)))
  );

  return (
    <div className="panel">
      <h2>本地脱敏样本预览</h2>
      <p className="desc">
        {catalog?.datasets?.[0]?.description ||
          "虚构的区间化脱敏样本：无姓名、联系方式、精确年龄与精确日期。"}
      </p>
      {err && <Alert kind="err">{err}</Alert>}
      {rows && (
        <table>
          <thead>
            <tr>
              <th>行号</th><th>参与者代号</th>
              {allKeys.map((k) => <th key={k}>{k}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.row_no}>
                <td>{r.row_no}</td>
                <td className="mono">{r.participant_code}</td>
                {allKeys.map((k) => <td key={k}>{String(r.payload[k] ?? "")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
