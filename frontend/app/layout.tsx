import "./globals.css";

export const metadata = {
  title: "研究数据平台 · 授权撤回演示",
  description: "参与者授权撤回后准确停止未来数据使用的端到端演示",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
