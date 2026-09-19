import "./globals.css";
import type { Metadata } from "next";
import { IdentityProvider } from "@/components/IdentityProvider";

export const metadata: Metadata = {
  title: "研究数据授权与撤回演示",
  description: "授权版本化 · 限时下载 · 参与者撤回 · 导出并发检查点",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <IdentityProvider>{children}</IdentityProvider>
      </body>
    </html>
  );
}
