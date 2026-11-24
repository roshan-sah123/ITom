import assert from "node:assert/strict";
import test from "node:test";
import type { AccountInfo } from "@azure/msal-browser";
import { finishSignIn, readSettings } from "../src/auth.ts";
import type { RedirectClient, RedirectResult } from "../src/auth.ts";

const tenantId = "11111111-2222-3333-4444-555555555555";
const env = {
  VITE_ENTRA_CLIENT_ID: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  VITE_ENTRA_TENANT_ID: tenantId,
  VITE_ENTRA_REDIRECT_URI: "http://localhost:5173/oauth2callback",
  VITE_PORTAL_URL: "http://localhost:5174/",
};
const account: AccountInfo = {
  homeAccountId: "test-home-account",
  localAccountId: "test-local-account",
  environment: "login.microsoftonline.com",
  tenantId,
  username: "operator@example.test",
};

function stubClient(result: RedirectResult | null, events: string[]): RedirectClient {
  return {
    async initialize() { events.push("initialize"); },
    async handleRedirectPromise(options) {
      assert.equal(options?.navigateToLoginRequestUrl, false);
      events.push("callback");
      return result;
    },
    setActiveAccount() { events.push("account"); },
  };
}

test("configuration requires explicit IDs, a matching callback origin and a safe portal URL outside the sign-in app", () => {
  const settings = readSettings(env, "http://localhost:5173");
  assert.equal(settings.redirectUri, env.VITE_ENTRA_REDIRECT_URI);
  assert.equal(settings.portalUrl, env.VITE_PORTAL_URL);
  for (const key of Object.keys(env)) {
    assert.throws(() => readSettings({ ...env, [key]: "" }, "http://localhost:5173"), /required/);
  }
  assert.throws(() => readSettings({ ...env, VITE_ENTRA_TENANT_ID: "common" }, "http://localhost:5173"), /tenant ID/i);
  assert.throws(() => readSettings({ ...env, VITE_ENTRA_CLIENT_ID: "not-an-id" }, "http://localhost:5173"), /client ID/i);
  assert.throws(() => readSettings(env, "http://127.0.0.1:5173"), /Open the sign-in app at http:\/\/localhost:5173/);
  assert.throws(() => readSettings({ ...env, VITE_ENTRA_REDIRECT_URI: "http://localhost:5173/wrong" }, "http://localhost:5173"), /oauth2callback/);
  for (const portal of ["javascript:alert(1)", "http://example.test/", "https://user:pass@example.test/", "http://localhost:5173/"]) {
    assert.throws(() => readSettings({ ...env, VITE_PORTAL_URL: portal }, "http://localhost:5173"));
  }
});

test("same-host deployment allows the portal root but never a portal URL that returns to the sign-in app", () => {
  const sameHost = {
    ...env,
    VITE_ENTRA_REDIRECT_URI: "https://itom.example.test/oauth2callback",
    VITE_PORTAL_URL: "https://itom.example.test/",
  };
  const settings = readSettings(sameHost, "https://itom.example.test", "/oauth2callback/");
  assert.equal(settings.portalUrl, "https://itom.example.test/");
  for (const portal of ["https://itom.example.test/oauth2callback", "https://itom.example.test/oauth2callback/", "https://itom.example.test/oauth2callback/assets/app.js"]) {
    assert.throws(() => readSettings({ ...sameHost, VITE_PORTAL_URL: portal }, "https://itom.example.test", "/oauth2callback/"), /sign-in app/);
  }
  assert.throws(() => readSettings(sameHost, "https://itom.example.test", "/"), /sign-in app/);
});

test("successful callback initializes MSAL, selects the account and opens only the configured portal", async () => {
  const events: string[] = [];
  const settings = readSettings(env, "http://localhost:5173");
  const client = stubClient({ tenantId, account }, events);
  const signedIn = await finishSignIn(client, settings, (url) => events.push(url));
  assert.equal(signedIn, true);
  assert.deepEqual(events, ["initialize", "callback", "account", "http://localhost:5174/"]);
});

test("visiting the login page without a completed response never opens the portal", async () => {
  const events: string[] = [];
  const client = stubClient(null, events);
  assert.equal(await finishSignIn(client, readSettings(env, "http://localhost:5173"), () => events.push("portal")), false);
  assert.deepEqual(events, ["initialize", "callback"]);
});

test("missing accounts and mismatched tenants never open the portal", async () => {
  for (const result of [
    { tenantId, account: null },
    { tenantId: "different-tenant", account },
    { tenantId, account: { ...account, tenantId: "different-tenant" } },
  ]) {
    const events: string[] = [];
    await assert.rejects(
      finishSignIn(stubClient(result, events), readSettings(env, "http://localhost:5173"), () => events.push("portal")),
      /account|tenant/i,
    );
    assert.deepEqual(events, ["initialize", "callback"]);
  }
});

test("MSAL initialization and callback errors propagate instead of redirecting", async () => {
  for (const stage of ["initialize", "handleRedirectPromise"] as const) {
    const events: string[] = [];
    const client = stubClient({ tenantId, account }, events);
    const failure = new Error("MSAL test failure");
    client[stage] = async () => { throw failure; };
    await assert.rejects(
      finishSignIn(client, readSettings(env, "http://localhost:5173"), () => events.push("portal")),
      (error) => error === failure,
    );
    assert.equal(events.includes("portal"), false);
    assert.equal(events.includes("account"), false);
  }
});
