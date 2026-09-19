export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const STORAGE_KEY = "consent-demo-identity";

export function getIdentity(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setIdentity(key: string | null) {
  if (typeof window === "undefined") return;
  if (key) window.localStorage.setItem(STORAGE_KEY, key);
  else window.localStorage.removeItem(STORAGE_KEY);
}

export async function apiFetch<T = any>(
  path: string,
  options: { method?: string; body?: any } = {}
): Promise<T> {
  const identity = getIdentity();
  const headers: Record<string, string> = {};
  if (identity) headers["X-Test-Identity"] = identity;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const message =
      data && typeof data === "object" && data.detail
        ? typeof data.detail === "string"
          ? data.detail
          : data.detail.message || data.detail.reason || JSON.stringify(data.detail)
        : `请求失败 (${res.status})`;
    const err = new Error(message) as Error & { status: number; data: any };
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data as T;
}

// 带身份头的下载链接 URL（浏览器 <a download> 无法加自定义头，
// 因此下载动作由前端 fetch 后保存为 Blob）
export async function downloadAsBlob(path: string): Promise<{ blob: Blob; filename: string }> {
  const identity = getIdentity();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: identity ? { "X-Test-Identity": identity } : {},
    cache: "no-store",
  });
  if (!res.ok) {
    let data: any = null;
    try {
      data = await res.json();
    } catch {}
    const message =
      data?.detail && typeof data.detail !== "string"
        ? data.detail.message || data.detail.reason
        : typeof data?.detail === "string"
        ? data.detail
        : `下载被拒绝 (${res.status})`;
    throw new Error(message);
  }
  const disposition = res.headers.get("content-disposition") || "";
  const m = /filename="?([^"]+)"?/.exec(disposition);
  const filename = m ? m[1] : "export.csv";
  return { blob: await res.blob(), filename };
}
