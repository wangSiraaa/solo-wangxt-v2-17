import Link from "next/link";
import PersonaNav from "./components/PersonaNav";
import { ResetDemoButton } from "./components/widgets";

const PERSONAS = [
  {
    role: "研究员",
    ids: [
      { id: "R-101", desc: "陈研（博士）· 国立心血管病中心" },
      { id: "R-102", desc: "帕特尔（博士）· 内分泌与代谢研究所" },
    ],
    href: "/researcher",
    todo: "申请数据集访问 → 获得限时授权 → 排队导出 → 下载数据",
  },
  {
    role: "数据管理员",
    ids: [{ id: "A-001", desc: "王数据（管理员）" }],
    href: "/admin",
    todo: "按用途审批申请、发放限时下载权限、查看审计事件、驱动导出队列",
  },
  {
    role: "参与者",
    ids: [
      { id: "P-001", desc: "受试者-001" },
      { id: "P-002", desc: "受试者-002" },
      { id: "P-003", desc: "受试者-003" },
    ],
    href: "/participant",
    todo: "查看授权范围与受影响项目 → 按用途撤回授权 → 观察导出取消与链接失效",
  },
];

export default function Home({
  searchParams,
}: {
  searchParams: { as?: string };
}) {
  const as = searchParams.as ?? "R-101";
  return (
    <>
      <PersonaNav as={as} />
      <div className="card">
        <h2>授权撤回演示平台</h2>
        <p className="sub">
          参与者撤回某类用途的授权后，平台准确停止其数据的未来使用：
          历史访问记录完整保留；尚未执行的导出任务立即取消；
          已发放的下载链接每次访问都重新校验授权并失效；
          导出执行前后各有一次权限检查点，覆盖"撤回与导出并发"的场景。
        </p>
        <ol className="flow-steps">
          <li>研究员提交数据集访问申请（指定用途）</li>
          <li>数据管理员批准，发放限时下载权限</li>
          <li>研究员排队导出，Worker 执行并签发限时下载链接</li>
          <li>参与者在独立门户撤回该用途授权</li>
          <li>排队中的导出被取消；执行中的导出在提交前检查点被拦截</li>
          <li>已发放的下载链接再次访问时被拒绝（403），全程留有审计记录</li>
        </ol>
        <ResetDemoButton />
      </div>

      <div className="grid cols-3">
        {PERSONAS.map((p) => (
          <div className="card" key={p.role}>
            <h3>{p.role}</h3>
            <p className="sub">{p.todo}</p>
            {p.ids.map((i) => (
              <p key={i.id} style={{ margin: "6px 0" }}>
                <Link href={`${p.href}?as=${i.id}`}>
                  {i.id} · {i.desc}
                </Link>
              </p>
            ))}
          </div>
        ))}
      </div>

      <div className="card">
        <h3>样本数据说明</h3>
        <p className="muted small" style={{ margin: 0 }}>
          所有参与者（P-001 ~ P-010）与生理指标均为本地生成的脱敏虚构数据。
          数据集 DS-CARDIO-2024（心血管队列，含 P-001~P-006）与
          DS-METAB-2024（代谢组学队列，含 P-004~P-010）。
          用途类别：心血管研究（cardio）、糖尿病研究（diabetes）、基因组分析（genomics）。
        </p>
      </div>
    </>
  );
}
