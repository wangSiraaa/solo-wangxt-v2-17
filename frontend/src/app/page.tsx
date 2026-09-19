"use client";

import { useEffect } from "react";
import { useIdentity } from "@/components/IdentityProvider";
import { useRouter } from "next/navigation";

export default function Home() {
  const { me, identities } = useIdentity();
  const router = useRouter();

  useEffect(() => {
    if (me) {
      const home: Record<string, string> = {
        participant: "/participant",
        researcher: "/researcher",
        admin: "/admin",
      };
      router.replace(home[me.role] || "/");
    }
  }, [me, router]);

  return (
    <div>
      <div className="panel">
        <h2>本地演示说明</h2>
        <p className="desc">
          这是一个研究数据“授予 — 访问 — 撤回”闭环演示。所有数据均为虚构、区间化脱敏样本，
          登录通过右上角切换<strong>测试身份</strong>完成（无密码，仅用于本地演示）。
        </p>
        <div className="grid2">
          <div>
            <h3>演示路径</h3>
            <ol className="small muted" style={{ paddingLeft: 18, lineHeight: 2 }}>
              <li>用 <b>研究员 R-2001</b> 选择数据集与用途，提交访问申请</li>
              <li>切换到 <b>管理员 A-3001</b> 按用途批准，授予限时下载窗口</li>
              <li>回到研究员页发起导出：任务先<strong>排队</strong>，worker 生成后出现下载链接</li>
              <li>切换到 <b>参与者 P-1001</b>（独立入口）撤回该用途授权</li>
              <li>回到研究员页：未完成任务被取消；已发链接重新校验后失效</li>
              <li>“访问事件”页展示全程只追加的审计记录</li>
            </ol>
          </div>
          <div>
            <h3>四个权限检查点</h3>
            <table>
              <tbody>
                <tr><td><span className="checkpoint">CP-1</span></td><td>导出入队：申请已批准、窗口未过期、全员当前授予</td></tr>
                <tr><td><span className="checkpoint">CP-2</span></td><td>导出执行：worker 写文件前持锁重新校验授权</td></tr>
                <tr><td><span className="checkpoint">CP-3</span></td><td>撤回生效：取消 queued/running 任务并撤销链接</td></tr>
                <tr><td><span className="checkpoint">CP-4</span></td><td>链接访问：每次下载都重新校验，不依赖旧快照</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>请选择一个测试身份开始</h2>
        <p className="desc">
          {identities.length === 0
            ? "无法连接后端，请确认 FastAPI 已在 8000 端口运行。"
            : "同一浏览器通过下拉框随时切换身份，模拟不同角色的操作视角。"}
        </p>
        <div className="grid2">
          {identities.map((i) => (
            <div key={i.identity_key} className="panel" style={{ margin: 0 }}>
              <div style={{ marginBottom: 8 }}>
                <span className={`badge ${i.role === "admin" ? "neutral" : i.role === "researcher" ? "complete" : "granted"}`}>
                  {i.role === "participant" ? "参与者" : i.role === "researcher" ? "研究员" : "数据管理员"}
                </span>
              </div>
              <div>{i.label}</div>
              <div className="mono muted small" style={{ marginTop: 4 }}>{i.identity_key}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
