import type { AccountInfo, HandleRedirectPromiseOptions } from "@azure/msal-browser";

export type Settings = {
  clientId: string;
  tenantId: string;
  redirectUri: string;
  portalUrl: string;
};

export type RedirectResult = {
  tenantId: string;
  account: AccountInfo | null;
};

export type RedirectClient = {
  initialize(): Promise<void>;
  handleRedirectPromise(options?: HandleRedirectPromiseOptions): Promise<RedirectResult | null>;
  setActiveAccount(account: AccountInfo): void;
};

export class SignInError extends Error {}

export function readSettings(env: Record<string, unknown>, origin: string, launcherPath = "/"): Settings {
  function required(key: string): string {
    const value = env[key];
    if (typeof value !== "string" || !value.trim()) {
      throw new SignInError(`${key} is required. Configure the standalone sign-in app and restart its server.`);
    }
    return value.trim();
  }

  function identifier(key: string, label: string): string {
    const value = required(key);
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
      throw new SignInError(`The ${label} must be the ID from your Entra app registration.`);
    }
    return value.toLowerCase();
  }

  function address(key: string, label: string): URL {
    const value = required(key);
    let url: URL;
    try {
      url = new URL(value);
    } catch {
      throw new SignInError(`${label} must be a valid absolute URL.`);
    }
    const localHttp = url.protocol === "http:" &&
      ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if ((!localHttp && url.protocol !== "https:") ||
        url.username || url.password || url.search || url.hash) {
      throw new SignInError(`${label} must use HTTPS (or local development HTTP), without credentials, query parameters or fragments.`);
    }
    return url;
  }

  const clientId = identifier("VITE_ENTRA_CLIENT_ID", "client ID");
  const tenantId = identifier("VITE_ENTRA_TENANT_ID", "tenant ID");
  const redirect = address("VITE_ENTRA_REDIRECT_URI", "Redirect URI");
  const portal = address("VITE_PORTAL_URL", "Portal URL");
  if (redirect.pathname !== "/oauth2callback") {
    throw new SignInError("The redirect URI must end with /oauth2callback.");
  }
  if (redirect.origin !== origin) {
    throw new SignInError(`Open the sign-in app at ${redirect.origin}. It must use the registered callback origin.`);
  }
  const launcher = new URL(launcherPath, redirect.origin).pathname;
  const returnsToLauncher = portal.pathname === launcher ||
    portal.pathname === redirect.pathname ||
    portal.pathname.startsWith(`${redirect.pathname}/`);
  if (portal.origin === redirect.origin && returnsToLauncher) {
    throw new SignInError("The portal URL must not point back to the sign-in app; that would cause a redirect loop.");
  }
  return { clientId, tenantId, redirectUri: redirect.href, portalUrl: portal.href };
}

export async function finishSignIn(
  client: RedirectClient,
  settings: Settings,
  openPortal: (url: string) => void,
): Promise<boolean> {
  await client.initialize();
  const result = await client.handleRedirectPromise({ navigateToLoginRequestUrl: false });
  if (!result) return false;
  if (!result.account) {
    throw new SignInError("Microsoft did not return an account. Restart sign-in.");
  }
  if (result.tenantId.toLowerCase() !== settings.tenantId ||
      result.account.tenantId.toLowerCase() !== settings.tenantId) {
    throw new SignInError("This account does not belong to the configured tenant. Sign in with your approved organizational account.");
  }
  client.setActiveAccount(result.account);
  openPortal(settings.portalUrl);
  return true;
}
