// Microsoft Entra ID sign-in for the portal. The backend validates the ID token
// and issues an HttpOnly session cookie that every same-origin API call carries.
import type { PublicClientApplication } from "@azure/msal-browser";

export type AuthConfig =
  | { enabled: false }
  | { enabled: true; tenantId: string; clientId: string; redirectPath: string; redirectUri?: string };

export type PortalUser = { name: string; username: string };

export class SignInError extends Error {}

const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const RETURN_KEY = "itom.signInReturnTo";

export function parseAuthConfig(value: unknown): AuthConfig {
  const data = (value ?? {}) as Record<string, unknown>;
  if (data.enabled !== true) return { enabled: false };
  const tenantId = String(data.tenant_id ?? "");
  const clientId = String(data.client_id ?? "");
  const redirectPath = String(data.redirect_path ?? "");
  if (!GUID.test(tenantId) || !GUID.test(clientId)) {
    throw new SignInError("Sign-in is enabled but the Entra tenant or client ID is invalid. Contact the portal administrator.");
  }
  if (!/^\/[a-z0-9/_-]+$/i.test(redirectPath)) {
    throw new SignInError("Sign-in is enabled but the callback path is invalid. Contact the portal administrator.");
  }
  const config: AuthConfig = { enabled: true, tenantId: tenantId.toLowerCase(), clientId: clientId.toLowerCase(), redirectPath };
  if (data.redirect_uri !== undefined) {
    let redirect: URL;
    try {
      redirect = new URL(String(data.redirect_uri));
    } catch {
      throw new SignInError("Sign-in is enabled but the redirect URI is invalid. Contact the portal administrator.");
    }
    const local = redirect.protocol === "http:" && ["localhost", "127.0.0.1"].includes(redirect.hostname);
    if ((redirect.protocol !== "https:" && !local) || redirect.pathname !== redirectPath || redirect.search || redirect.hash) {
      throw new SignInError("Sign-in is enabled but the redirect URI is invalid. Contact the portal administrator.");
    }
    config.redirectUri = redirect.href;
  }
  return config;
}

/** The registered sign-in origin when this page was opened on another address (e.g. HTTP or an IP). */
export function canonicalLocation(config: Extract<AuthConfig, { enabled: true }>, location: { origin: string; pathname: string; search: string; hash: string }): string | null {
  if (!config.redirectUri) return null;
  const origin = new URL(config.redirectUri).origin;
  return origin === location.origin ? null : `${origin}${location.pathname}${location.search}${location.hash}`;
}

export function msalSettings(config: Extract<AuthConfig, { enabled: true }>, origin: string) {
  const redirectUri = config.redirectUri ?? new URL(config.redirectPath, origin).href;
  return {
    clientId: config.clientId,
    authority: `https://login.microsoftonline.com/${config.tenantId}`,
    redirectUri,
    postLogoutRedirectUri: redirectUri,
  };
}

/** Accept only sign-ins for an account in the configured tenant. */
export function verifiedIdToken(
  result: { tenantId: string; idToken: string; account: { tenantId: string } | null } | null,
  tenantId: string,
): string | null {
  if (!result) return null;
  if (!result.account || !result.idToken) {
    throw new SignInError("Microsoft did not return an account. Restart sign-in.");
  }
  if (result.tenantId.toLowerCase() !== tenantId || result.account.tenantId.toLowerCase() !== tenantId) {
    throw new SignInError("This account does not belong to the configured organization. Sign in with your approved organizational account.");
  }
  return result.idToken;
}

export function signInErrorMessage(error: unknown): string {
  if (error instanceof SignInError) return error.message;
  const code = (error as { errorCode?: unknown })?.errorCode;
  if (typeof code === "string") {
    const safeCode = /^[a-z0-9_]{1,80}$/i.test(code) ? code : "authentication_error";
    const entraCode = String((error as Error).message ?? "").match(/\bAADSTS\d+\b/)?.[0];
    return `Microsoft sign-in could not complete (${safeCode}${entraCode ? `, ${entraCode}` : ""}). Check your account access and network connection, then try again.`;
  }
  return "Sign-in could not complete. Check your browser and network connection, then try again.";
}

export function isProtectedApiRequest(input: RequestInfo | URL, base: string): boolean {
  const url = typeof input === "string" || input instanceof URL ? input : input.url;
  const path = new URL(url, base).pathname;
  return path.startsWith("/api/") && !path.startsWith("/api/v1/auth/");
}

async function authRequest(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`/api/v1/auth${path}`, {
    ...init,
    cache: "no-store",
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    signal: AbortSignal.timeout(20000),
  });
}

async function authError(response: Response, fallback: string): Promise<SignInError> {
  const detail = await response.json().then((body) => body?.detail).catch(() => undefined);
  return new SignInError(typeof detail === "string" ? detail : fallback);
}

export async function loadAuthConfig(): Promise<AuthConfig> {
  const response = await authRequest("/config");
  if (!response.ok) throw await authError(response, "The sign-in service is unavailable. Retry shortly.");
  return parseAuthConfig(await response.json());
}

export async function currentUser(): Promise<PortalUser | null> {
  const response = await authRequest("/me");
  if (!response.ok) throw await authError(response, "The sign-in service is unavailable. Retry shortly.");
  const body = await response.json();
  if (body.authenticated !== true) return null;
  return { name: String(body.name ?? ""), username: String(body.username ?? "") };
}

export async function startSession(idToken: string): Promise<PortalUser> {
  const response = await authRequest("/session", { method: "POST", body: JSON.stringify({ id_token: idToken }) });
  if (!response.ok) throw await authError(response, "The portal could not verify your Microsoft sign-in.");
  const body = await response.json();
  return { name: String(body.name ?? ""), username: String(body.username ?? "") };
}

export async function endSession(): Promise<void> {
  await authRequest("/logout", { method: "POST" }).catch(() => undefined);
}

export async function createMsalClient(config: Extract<AuthConfig, { enabled: true }>): Promise<PublicClientApplication> {
  const { BrowserCacheLocation, PublicClientApplication } = await import("@azure/msal-browser");
  const client = new PublicClientApplication({
    auth: msalSettings(config, window.location.origin),
    cache: { cacheLocation: BrowserCacheLocation.SessionStorage },
  });
  await client.initialize();
  return client;
}

export function rememberReturnPath(): void {
  const { pathname, search } = window.location;
  sessionStorage.setItem(RETURN_KEY, pathname === "/oauth2callback" ? "/" : `${pathname}${search}`);
}

export function takeReturnPath(): string {
  const value = sessionStorage.getItem(RETURN_KEY) ?? "/";
  sessionStorage.removeItem(RETURN_KEY);
  return value.startsWith("/") && !value.startsWith("//") ? value : "/";
}
