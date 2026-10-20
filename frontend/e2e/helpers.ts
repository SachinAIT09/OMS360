import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const OPS = { email: "dana.whitaker@prairieskypower.example", password: "oms360" };

/** Sign in through the API and hand the token to the page (fast path for every test but the login journey). */
export async function signIn(page: Page, request: APIRequestContext, who = OPS) {
  const r = await request.post("/api/auth/login", { data: who });
  expect(r.ok()).toBeTruthy();
  const { token } = await r.json();
  await page.addInitScript(t => localStorage.setItem("oms360_token", t), token);
  return token as string;
}

export async function api<T>(request: APIRequestContext, token: string, path: string): Promise<T> {
  const r = await request.get(`/api${path}`, { headers: { Authorization: `Bearer ${token}` } });
  expect(r.ok(), `${path} → ${r.status()}`).toBeTruthy();
  return r.json() as Promise<T>;
}

/** Collect uncaught page errors and console errors (third-party tile / weather failures excluded) for the test to assert on. */
export function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(`pageerror: ${e.message}`));
  page.on("console", m => {
    if (m.type() !== "error") return;
    const t = m.text();
    if (/Failed to load resource|arcgisonline|openstreetmap|open-meteo|openweathermap|ERR_|net::/i.test(t)) return;
    errors.push(`console: ${t}`);
  });
  return errors;
}

/** True when the page scrolls sideways (a layout overflowing the viewport). */
export async function overflowsX(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
}
