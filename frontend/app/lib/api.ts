/** 服务端组件用（容器内走内网地址），客户端组件用 NEXT_PUBLIC_API_URL。 */
export const API = process.env.API_URL ?? "http://localhost:8000";
export const PUBLIC_API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string, as: string): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    cache: "no-store",
    headers: { "X-User-Id": as },
  });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}
