import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { PublicClientApplication } from "@azure/msal-browser";
import {
  canonicalLocation,
  createMsalClient,
  currentUser,
  endSession,
  isProtectedApiRequest,
  loadAuthConfig,
  rememberReturnPath,
  signInErrorMessage,
  startSession,
  takeReturnPath,
  verifiedIdToken,
} from "./auth";
import type { AuthConfig, PortalUser } from "./auth";

type EnabledConfig = Extract<AuthConfig, { enabled: true }>;
type State =
  | { status: "checking" }
  | { status: "open" }
  | { status: "signed-in"; config: EnabledConfig; user: PortalUser }
  | { status: "signed-out"; config: EnabledConfig; message?: string }
  | { status: "error"; message: string };

export type PortalAuth = { user: PortalUser | null; signOut?: () => void };

function SignInFrame({ children }: { children: ReactNode }) {
  return (
    <main className="sso-page">
      <section className="sso-card" aria-labelledby="sso-heading">
        <header className="sso-card__brand">
          <img alt="Coforge" src="/coforge-logo.png" />
          <span>ITOM</span>
        </header>
        <p className="sso-card__eyebrow">OPERATIONS INTELLIGENCE</p>
        <h1 id="sso-heading">Sign in to ITOM</h1>
        <p className="sso-card__intro">Use your organizational Microsoft account to continue to the portal.</p>
        {children}
        <p className="sso-card__privacy">Your password and multifactor authentication are handled by Microsoft, not this application.</p>
      </section>
    </main>
  );
}

export default function AuthGate({ children }: { children: (auth: PortalAuth) => ReactNode }) {
  // The server marks the page when SSO is off, so the portal renders without waiting.
  const [ssoOff] = useState(() => document.querySelector('meta[name="itom-auth"]')?.getAttribute("content") === "off");
  const [state, setState] = useState<State>(ssoOff ? { status: "open" } : { status: "checking" });
  const [busy, setBusy] = useState(false);
  const client = useRef<PublicClientApplication | null>(null);

  const msal = useCallback(async (config: EnabledConfig) => {
    client.current ??= await createMsalClient(config);
    return client.current;
  }, []);

  const resolve = useCallback(async () => {
    setState({ status: "checking" });
    try {
      const config = await loadAuthConfig();
      if (!config.enabled) {
        setState({ status: "open" });
        return;
      }
      const canonical = canonicalLocation(config, window.location);
      if (canonical) {
        window.location.replace(canonical);
        return;
      }
      if (window.location.pathname === config.redirectPath) {
        const instance = await msal(config);
        const result = await instance.handleRedirectPromise({ navigateToLoginRequestUrl: false });
        const idToken = verifiedIdToken(result, config.tenantId);
        if (idToken && result?.account) {
          instance.setActiveAccount(result.account);
          const user = await startSession(idToken);
          window.history.replaceState(null, "", takeReturnPath());
          setState({ status: "signed-in", config, user });
          return;
        }
        window.history.replaceState(null, "", "/");
      }
      const user = await currentUser();
      setState(user ? { status: "signed-in", config, user } : { status: "signed-out", config });
    } catch (error) {
      if (window.location.pathname === "/oauth2callback") window.history.replaceState(null, "", "/");
      setState({ status: "error", message: signInErrorMessage(error) });
    }
  }, [msal]);

  useEffect(() => {
    if (!ssoOff) void resolve();
  }, [resolve, ssoOff]);

  // An API 401 means the portal session expired or was revoked; return to sign-in.
  const signedInConfig = state.status === "signed-in" ? state.config : null;
  useEffect(() => {
    if (!signedInConfig) return;
    const original = window.fetch;
    window.fetch = async (input, init) => {
      const response = await original(input, init);
      if (response.status === 401 && isProtectedApiRequest(input, window.location.href)) {
        setState({ status: "signed-out", config: signedInConfig, message: "Your session has ended. Sign in again to continue." });
      }
      return response;
    };
    return () => {
      window.fetch = original;
    };
  }, [signedInConfig]);

  async function signIn(config: EnabledConfig) {
    if (busy) return;
    setBusy(true);
    try {
      rememberReturnPath();
      await (await msal(config)).loginRedirect({ scopes: ["openid", "profile", "email"] });
    } catch (error) {
      setState({ status: "signed-out", config, message: signInErrorMessage(error) });
      setBusy(false);
    }
  }

  const signOut = useCallback(async () => {
    if (state.status !== "signed-in") return;
    const { config } = state;
    await endSession();
    try {
      await (await msal(config)).logoutRedirect();
    } catch {
      setState({ status: "signed-out", config, message: "You have been signed out of the portal." });
    }
  }, [msal, state]);

  if (state.status === "open") return <>{children({ user: null })}</>;
  if (state.status === "signed-in") return <>{children({ user: state.user, signOut: () => void signOut() })}</>;
  if (state.status === "checking") {
    return <SignInFrame><p className="sso-card__status" role="status">Checking sign-in…</p></SignInFrame>;
  }
  if (state.status === "error") {
    return (
      <SignInFrame>
        <p className="sso-card__error" role="alert">{state.message}</p>
        <button className="sso-card__primary" onClick={() => void resolve()} type="button">Try again</button>
      </SignInFrame>
    );
  }
  return (
    <SignInFrame>
      {state.message && <p className="sso-card__error" role="alert">{state.message}</p>}
      <button className="sso-card__primary" disabled={busy} onClick={() => void signIn(state.config)} type="button">
        {busy ? "Connecting to Microsoft…" : "Sign in with Microsoft"}
      </button>
      {busy && <p className="sso-card__status" role="status">Please wait while Microsoft sign-in opens.</p>}
    </SignInFrame>
  );
}
