import test from "node:test";
import assert from "node:assert/strict";
import {
  SignInError,
  canonicalLocation,
  isProtectedApiRequest,
  msalSettings,
  parseAuthConfig,
  signInErrorMessage,
  verifiedIdToken,
} from "../src/auth.ts";

const tenant = "b727a530-a0d5-4fb8-bd40-d8f9763e97db";
const client = "594702a7-2bd8-4692-95bc-cbcd9f28424f";
const enabled = { enabled: true, tenant_id: tenant.toUpperCase(), client_id: client, redirect_path: "/oauth2callback" };

test("disabled or missing sign-in configuration leaves the portal open", () => {
  assert.deepEqual(parseAuthConfig({ enabled: false }), { enabled: false });
  assert.deepEqual(parseAuthConfig(null), { enabled: false });
});

test("enabled configuration is normalized and validated", () => {
  assert.deepEqual(parseAuthConfig(enabled), { enabled: true, tenantId: tenant, clientId: client, redirectPath: "/oauth2callback" });
  assert.throws(() => parseAuthConfig({ ...enabled, client_id: "not-a-guid" }), SignInError);
  assert.throws(() => parseAuthConfig({ ...enabled, redirect_path: "https://evil.example/cb" }), SignInError);
});

test("MSAL uses the tenant authority and a same-origin callback", () => {
  const config = parseAuthConfig(enabled);
  assert.equal(config.enabled, true);
  if (!config.enabled) return;
  assert.deepEqual(msalSettings(config, "http://localhost:8081"), {
    clientId: client,
    authority: `https://login.microsoftonline.com/${tenant}`,
    redirectUri: "http://localhost:8081/oauth2callback",
    postLogoutRedirectUri: "http://localhost:8081/oauth2callback",
  });
});

test("a configured redirect URI pins sign-in to the registered HTTPS origin", () => {
  const config = parseAuthConfig({ ...enabled, redirect_uri: "https://itom.coforge.com/oauth2callback" });
  assert.equal(config.enabled, true);
  if (!config.enabled) return;
  assert.equal(msalSettings(config, "http://172.18.51.38").redirectUri, "https://itom.coforge.com/oauth2callback");
  const page = (origin: string) => ({ origin, pathname: "/", search: "?attachment=1", hash: "" });
  assert.equal(canonicalLocation(config, page("http://172.18.51.38")), "https://itom.coforge.com/?attachment=1");
  assert.equal(canonicalLocation(config, page("http://itom.coforge.com")), "https://itom.coforge.com/?attachment=1");
  assert.equal(canonicalLocation(config, page("https://itom.coforge.com")), null);
  assert.throws(() => parseAuthConfig({ ...enabled, redirect_uri: "http://itom.coforge.com/oauth2callback" }), SignInError);
  assert.throws(() => parseAuthConfig({ ...enabled, redirect_uri: "https://itom.coforge.com/elsewhere" }), SignInError);
});

test("only accounts from the configured tenant are accepted", () => {
  assert.equal(verifiedIdToken(null, tenant), null);
  const result = { tenantId: tenant.toUpperCase(), idToken: "header.payload.signature", account: { tenantId: tenant } };
  assert.equal(verifiedIdToken(result, tenant), "header.payload.signature");
  assert.throws(() => verifiedIdToken({ ...result, account: null }, tenant), /did not return an account/);
  assert.throws(() => verifiedIdToken({ ...result, tenantId: "00000000-0000-0000-0000-000000000000" }, tenant), /configured organization/);
  assert.throws(() => verifiedIdToken({ ...result, account: { tenantId: "00000000-0000-0000-0000-000000000000" } }, tenant), /configured organization/);
});

test("sign-in errors are summarized without echoing raw messages", () => {
  assert.equal(signInErrorMessage(new SignInError("Configured message")), "Configured message");
  const msal = Object.assign(new Error("AADSTS50105: user <script> not assigned"), { errorCode: "access_denied" });
  assert.match(signInErrorMessage(msal), /access_denied, AADSTS50105/);
  assert.doesNotMatch(signInErrorMessage(msal), /script/);
  assert.match(signInErrorMessage(new Error("boom")), /Sign-in could not complete/);
});

test("only protected API requests trigger re-authentication", () => {
  const base = "http://localhost:8081/";
  assert.equal(isProtectedApiRequest("/api/v1/cmdb/summary", base), true);
  assert.equal(isProtectedApiRequest("/api/v1/auth/me", base), false);
  assert.equal(isProtectedApiRequest("/revamp-assets/app.js", base), false);
  assert.equal(isProtectedApiRequest(new URL("http://localhost:8081/api/v1/assets/summary"), base), true);
});
