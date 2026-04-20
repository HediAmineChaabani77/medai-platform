const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const TOKEN_KEY = "medai_access_token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

function withAuth(init?: RequestInit): RequestInit {
  const token = getAuthToken();
  const headers = new Headers(init?.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...(init || {}), headers };
}

export const api = {
  get: async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const r = await fetch(`${API}${path}`, { cache: "no-store", ...withAuth(init) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err: any = new Error(`GET ${path} ${r.status}`);
      err.status = r.status;
      err.body = data;
      throw err;
    }
    return data as T;
  },
  post: async <T,>(path: string, body: unknown): Promise<T> => {
    const init = withAuth({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const r = await fetch(`${API}${path}`, {
      ...init,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err: any = new Error(`POST ${path} ${r.status}`);
      err.status = r.status; err.body = data;
      throw err;
    }
    return data as T;
  },
  postForm: async <T,>(path: string, form: FormData): Promise<T> => {
    const r = await fetch(`${API}${path}`, withAuth({ method: "POST", body: form }));
    if (!r.ok) throw new Error(`POST ${path} ${r.status}`);
    return r.json();
  },
  del: async <T,>(path: string): Promise<T> => {
    const r = await fetch(`${API}${path}`, withAuth({ method: "DELETE" }));
    if (!r.ok) throw new Error(`DELETE ${path} ${r.status}`);
    return r.json();
  },
};
