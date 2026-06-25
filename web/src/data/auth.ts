// Auth client for the console. The session token is stored in the browser, but
// the *role* lives inside the server-signed token and is re-validated against
// /auth/me — so a user can't escalate by editing localStorage.

export type Role = "sales" | "manager" | "store_manager" | "area_manager" | "admin";

export type ManagerRole = "manager" | "store_manager" | "area_manager" | "admin";

export interface User {
  email: string;
  name: string;
  role: Role;
  tenant: string;
  user_id?: string;
}

export interface SignupInput {
  name: string;
  email: string;
  password: string;
  role: Role;
  org?: string;
  invite?: string;
}

const TOKEN_KEY = "voclyp_session_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail || detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<{ token: string; user: User }> {
  return post("/auth/login", { email, password });
}

export async function signup(input: SignupInput): Promise<{ token: string; user: User }> {
  return post("/auth/signup", input);
}

export async function fetchMe(): Promise<User | null> {
  if (!getToken()) return null;
  const resp = await fetch("/auth/me", { headers: authHeaders() });
  if (!resp.ok) return null;
  return (await resp.json()).user as User;
}

export async function logout(): Promise<void> {
  if (getToken()) {
    try {
      await fetch("/auth/logout", { method: "POST", headers: authHeaders() });
    } catch {
      /* network error — clear locally anyway */
    }
  }
  clearToken();
}

export async function createInvite(role: Role): Promise<string> {
  const resp = await fetch("/auth/invite", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ role }),
  });
  if (!resp.ok) {
    throw new Error((await resp.json().catch(() => ({}))).detail || "could not create invite");
  }
  return (await resp.json()).invite as string;
}

export function isManagerRole(role: Role): role is ManagerRole {
  return role === "manager" || role === "store_manager" || role === "area_manager" || role === "admin";
}

export function homeFor(role: Role): string {
  if (isManagerRole(role)) return "/manager/live";
  return "/field";
}

export function roleLabel(role: Role): string {
  switch (role) {
    case "area_manager":
      return "Area manager";
    case "store_manager":
      return "Store manager";
    case "admin":
      return "Admin";
    case "manager":
      return "Manager";
    default:
      return "Sales rep";
  }
}

export function parseRole(value: string | null): Role | null {
  const roles: Role[] = ["manager", "sales", "store_manager", "area_manager", "admin"];
  return roles.includes(value as Role) ? (value as Role) : null;
}
