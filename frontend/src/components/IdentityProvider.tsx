"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, getIdentity, setIdentity } from "@/lib/api";

type Identity = { identity_key: string; role: string; label: string };
type Me = { identity_key: string; role: string; label: string };

type Ctx = {
  identities: Identity[];
  me: Me | null;
  switchIdentity: (key: string | null) => void;
  refresh: () => void;
  refreshTick: number;
};

const IdentityCtx = createContext<Ctx>({
  identities: [],
  me: null,
  switchIdentity: () => {},
  refresh: () => {},
  refreshTick: 0,
});

export function useIdentity() {
  return useContext(IdentityCtx);
}

const ROLE_HOME: Record<string, string> = {
  participant: "/participant",
  researcher: "/researcher",
  admin: "/admin",
};

export function IdentityProvider({ children }: { children: ReactNode }) {
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [tick, setTick] = useState(0);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    apiFetch<Identity[]>("/api/identities").then(setIdentities).catch(() => {});
  }, []);

  useEffect(() => {
    const key = getIdentity();
    if (!key) {
      setMe(null);
      return;
    }
    apiFetch<Me>("/api/me")
      .then(setMe)
      .catch(() => setMe(null));
  }, [tick]);

  function switchIdentity(key: string | null) {
    setIdentity(key);
    setTick((t) => t + 1);
    if (key) {
      apiFetch<Me>("/api/me")
        .then((m) => {
          setMe(m);
          if (pathname === "/") router.push(ROLE_HOME[m.role] || "/");
        })
        .catch(() => {});
    } else {
      setMe(null);
    }
  }

  const nav = me ? (
    <nav className="nav">
      {me.role === "researcher" && (
        <>
          <Link href="/researcher">我的项目</Link>
          <Link href="/researcher/new">新建申请</Link>
        </>
      )}
      {me.role === "admin" && <Link href="/admin">审批与队列</Link>}
      {me.role === "participant" && <Link href="/participant">我的授权</Link>}
      <Link href="/sample">脱敏样本</Link>
      <Link href="/events">访问事件</Link>
    </nav>
  ) : null;

  return (
    <IdentityCtx.Provider
      value={{ identities, me, switchIdentity, refresh: () => setTick((t) => t + 1), refreshTick: tick }}
    >
      <header className="topbar">
        <div className="inner">
          <div>
            <h1>研究数据授权与撤回演示平台</h1>
            <div className="sub">脱敏样本 · 限时下载授权 · 撤回检查点 CP-1 ~ CP-4</div>
          </div>
          {nav}
          <select
            value={me?.identity_key || ""}
            onChange={(e) => switchIdentity(e.target.value || null)}
            title="切换测试身份"
          >
            <option value="">— 选择测试身份 —</option>
            {identities.map((i) => (
              <option key={i.identity_key} value={i.identity_key}>
                {i.label}
              </option>
            ))}
          </select>
        </div>
      </header>
      <main className="container">{children}</main>
    </IdentityCtx.Provider>
  );
}
