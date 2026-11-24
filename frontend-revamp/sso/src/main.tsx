import { StrictMode, useState } from "react";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { AuthError, BrowserCacheLocation, PublicClientApplication } from "@azure/msal-browser";
import { finishSignIn, readSettings, SignInError } from "./auth";
import type { Settings } from "./auth";
import "./styles.css";

function errorMessage(error: unknown): string {
  if (error instanceof SignInError) return error.message;
  if (error instanceof AuthError) {
    const code = /^[a-z0-9_]{1,80}$/i.test(error.errorCode) ? error.errorCode : "authentication_error";
    const entraCode = error.message.match(/\bAADSTS\d+\b/)?.[0];
    return `Microsoft sign-in could not complete (${code}${entraCode ? `, ${entraCode}` : ""}). Check the app registration, account access and network connection, then try again.`;
  }
  return "Sign-in could not complete. Check your browser and network connection, then restart sign-in.";
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <main>
      <section className="sign-in-card" aria-labelledby="sign-in-heading">
        <header>
          <span className="brand">Coforge</span>
          <span className="product">ITOM</span>
        </header>
        <p className="eyebrow">OPERATIONS INTELLIGENCE</p>
        <h1 id="sign-in-heading">Sign in to ITOM</h1>
        <p className="intro">Use your organizational Microsoft account to continue to the portal.</p>
        {children}
        <p className="privacy">Your password and multifactor authentication are handled by Microsoft, not this application.</p>
      </section>
      <aside aria-label="Standalone sign-in limitation">
        Sign-in launcher only. Direct portal access remains available; this does not protect portal data or APIs.
      </aside>
    </main>
  );
}

function SignIn({ client, settings }: { client: PublicClientApplication; settings: Settings }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hasAccount = client.getAllAccounts().length > 0;

  async function interact(action: "login" | "logout") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (action === "login") {
        await client.loginRedirect({ scopes: ["openid", "profile", "email"] });
      } else {
        await client.logoutRedirect({ postLogoutRedirectUri: settings.redirectUri });
      }
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  return (
    <Frame>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={busy} onClick={() => void interact("login")}>
        {busy ? "Connecting to Microsoft..." : "Sign in with Microsoft"}
      </button>
      {busy && <p className="status" role="status">Please wait while Microsoft sign-in opens.</p>}
      {hasAccount && (
        <button className="secondary" disabled={busy} onClick={() => void interact("logout")}>
          Sign out of Microsoft
        </button>
      )}
      <p className="destination">After sign-in: <span>{settings.portalUrl}</span></p>
    </Frame>
  );
}

const element = document.getElementById("root");
if (!element) throw new Error("The sign-in application root is missing.");
const root = createRoot(element);

async function start() {
  root.render(<Frame><p role="status">Checking sign-in response...</p></Frame>);
  try {
    const settings = readSettings(import.meta.env, window.location.origin, import.meta.env.BASE_URL);
    const client = new PublicClientApplication({
      auth: {
        clientId: settings.clientId,
        authority: `https://login.microsoftonline.com/${settings.tenantId}`,
        redirectUri: settings.redirectUri,
        postLogoutRedirectUri: settings.redirectUri,
      },
      cache: { cacheLocation: BrowserCacheLocation.SessionStorage },
    });
    // Initialize and consume the callback once, outside React's development effect replay.
    const redirected = await finishSignIn(client, settings, (url) => window.location.replace(url));
    if (redirected) {
      root.render(<Frame><p role="status">Sign-in complete. Opening the portal...</p></Frame>);
    } else {
      root.render(<StrictMode><SignIn client={client} settings={settings} /></StrictMode>);
    }
  } catch (error) {
    root.render(
      <Frame>
        <p className="error" role="alert">{errorMessage(error)}</p>
        <a className="primary" href={import.meta.env.BASE_URL}>Restart sign-in</a>
      </Frame>,
    );
  }
}

void start();
