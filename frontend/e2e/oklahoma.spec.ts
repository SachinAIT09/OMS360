/* End-to-end journeys for the Oklahoma tornado scenario and asset intelligence (scenarios 1–9 of the acceptance plan). */
import { expect, test } from "@playwright/test";
import { api, OPS, overflowsX, signIn, watchErrors } from "./helpers";

type Ev = { id: number; name: string; kind: string };
type Unit = { id: string; kind: string; feeder_id: string | null; install_year: number | null; age: number | null; health_index: number | null; condition: string };
const fmt = (n: number) => Math.round(n).toLocaleString("en-US");

async function current(request: Parameters<typeof api>[0], token: string) { return api<Ev>(request, token, "/events/current"); }



test("1. sign in and see the Oklahoma tornado scenario", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/login");
  await page.getByLabel("EMAIL").fill(OPS.email);
  await page.getByLabel("PASSWORD").fill(OPS.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Central Oklahoma Tornado Outbreak").first()).toBeVisible();
  await expect(page.getByText("Prairie Sky Power").first()).toBeVisible();
  await expect(page.getByText("Simulation data").first()).toBeVisible();
  await expect(page.getByText(/Network impact/)).toBeVisible();
  await expect(page.locator(".leaflet-container").first()).toBeVisible();
  await expect(page.locator(".twister").first()).toBeAttached();  // tornado marker on the map
  expect(errors).toEqual([]);
});

test("1b. storm map: damage paths, timeline and layer toggles", async ({ page, request }) => {
  const token = await signIn(page, request);
  const ev = await current(request, token);
  const errors = watchErrors(page);
  await page.goto(`/events/${ev.id}`);
  await expect(page.getByText("EF rating (main tornado)")).toBeVisible();
  await expect(page.getByText("Touchdown", { exact: true })).toBeVisible();
  await expect(page.locator(".twister")).toHaveCount(2);  // one per damage path
  await expect(page.getByText("Timeline: now")).toBeVisible();
  const thumb = page.getByRole("slider").first();
  await thumb.focus();
  for (let i = 0; i < 12; i++) await page.keyboard.press("ArrowRight");
  await expect(page.getByText(/Timeline: \d+:\d\d (AM|PM)/)).toBeVisible();
  await page.getByRole("button", { name: "Now", exact: true }).click();
  await expect(page.getByText("Timeline: now")).toBeVisible();

  await page.goto("/network");
  await expect(page.locator(".twister").first()).toBeAttached();
  await page.getByText("Storm paths", { exact: true }).click();  // layer off
  await expect(page.locator(".twister")).toHaveCount(0);
  await page.getByText("Storm paths", { exact: true }).click();  // and back on
  await expect(page.locator(".twister").first()).toBeAttached();
  expect(errors).toEqual([]);
});

test("2. regional drill-down and back to the whole state", async ({ page, request }) => {
  const token = await signIn(page, request);
  const central = await api<{ all: { units: number } }>(request, token, "/assets/summary?region=central");
  await page.goto("/network");
  await expect(page.getByText("Click a region on the map or in the table to drill in.")).toBeVisible();
  await page.getByRole("row", { name: /^Central/ }).click();
  await expect(page).toHaveURL(/region=central/);
  await expect(page.getByText("Central region", { exact: true })).toBeVisible();
  await expect(page.getByText(/^Substations \(\d+\)/)).toBeVisible();
  await expect(page.getByText(fmt(central.all.units), { exact: true })).toBeVisible();  // KPI from the same data as the API
  await page.getByRole("button", { name: "Whole territory" }).click();
  await expect(page).not.toHaveURL(/region=/);
  await expect(page.getByText("Click a region on the map or in the table to drill in.")).toBeVisible();
});

test("3. circuit drill-down to a transformer with the right parents", async ({ page, request }) => {
  const token = await signIn(page, request);
  const subs = await api<{ id: string; name: string }[]>(request, token, "/network/substations?region=central");
  const sub = subs[0];
  const detail = await api<{ circuits_detail: { id: string }[] }>(request, token, `/network/substations/${sub.id}`);
  const fid = detail.circuits_detail[0].id;
  await page.goto("/network?region=central");
  await page.getByRole("row", { name: new RegExp(`^${sub.name}`) }).click();
  await expect(page).toHaveURL(new RegExp(`sub=${sub.id}`));
  await expect(page.getByText("Substation equipment")).toBeVisible();
  await page.getByRole("row", { name: new RegExp(`^${fid}`) }).click();  // the circuit row, not the feeder breaker named after it
  await expect(page).toHaveURL(new RegExp(`circuit=${fid}`));
  await expect(page.getByText("Equipment on this circuit")).toBeVisible();
  const firstUnit = page.locator("table").last().locator("tbody tr").first();
  const unitId = (await firstUnit.locator("p").first().textContent())!.trim();
  await firstUnit.click();
  await expect(page).toHaveURL(new RegExp(`asset=${unitId}`));
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText(`Unit ${unitId}`)).toBeVisible();
  await expect(drawer.getByRole("link", { name: fid })).toBeVisible();  // breadcrumb parent
  const unit = await api<Unit>(request, token, `/assets/item/${unitId}`);
  expect(unit.feeder_id).toBe(fid);
  await drawer.getByRole("button", { name: "Close unit details" }).click();
  await expect(page).not.toHaveURL(/asset=/);
  await expect(page).toHaveURL(new RegExp(`circuit=${fid}`));
});

test("4. transformer age, health and missing data", async ({ page, request }) => {
  const token = await signIn(page, request);
  const [poor] = await api<Unit[]>(request, token, "/assets/top?kind=dist_transformer&condition=Poor&n=1");
  const expectedAge = new Date().getFullYear() - poor.install_year!;  // independent of the app's own calculation
  await page.goto(`/asset/${poor.id}`);
  await expect(page.getByText(`${expectedAge} y`, { exact: true }).first()).toBeVisible();
  await expect(page.getByText(`installed ${poor.install_year}`, { exact: false }).first()).toBeVisible();
  await expect(page.getByText(String(Math.round(poor.health_index!)), { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Why this health index")).toBeVisible();
  await expect(page.getByText(/Illustrative model/).first()).toBeVisible();

  const [unknown] = await api<Unit[]>(request, token, "/assets/top?kind=dist_transformer&condition=Unknown&n=1");
  expect(unknown.health_index).toBeNull();
  await page.goto(`/asset/${unknown.id}`);
  await expect(page.getByText("Unknown").first()).toBeVisible();
  await expect(page.getByText(/Install year not recorded/).first()).toBeVisible();
  await expect(page.getByText(/estimated from a typical age/).first()).toBeVisible();
  await expect(page.getByText(/^HI \d+/)).toHaveCount(0);  // no health score is shown for it
});

test("5. filters stay consistent across cards, tables and the map", async ({ page, request }) => {
  const token = await signIn(page, request);
  const central = await api<{ distribution: { units: number } }>(request, token, "/assets/summary?region=central");
  const ne = await api<{ distribution: { units: number } }>(request, token, "/assets/summary?region=northeast");
  await page.goto("/asset-health");
  await page.getByRole("textbox", { name: "Region" }).click();
  await page.getByRole("option", { name: "Central region" }).click();
  await expect(page.getByText("Showing Central region")).toBeVisible();
  await expect(page.getByText(fmt(central.distribution.units), { exact: true }).first()).toBeVisible();
  const zoneCells = page.locator("table").last().locator("tbody tr td:nth-child(2) p:last-child");
  await expect(zoneCells.first()).toContainText("Central");
  for (const t of await zoneCells.allTextContents()) expect(t).toContain("Central");
  await page.getByRole("textbox", { name: "Region" }).click();
  await page.getByRole("option", { name: "Northeast region" }).click();
  await expect(page.getByText("Showing Northeast region")).toBeVisible();
  await expect(page.getByText(fmt(ne.distribution.units), { exact: true }).first()).toBeVisible();
  await expect(zoneCells.first()).toContainText("Northeast");
  for (const t of await zoneCells.allTextContents()) expect(t).not.toContain("Central");

  // changing the region in the explorer drops the circuit and unit picked under the old one
  const cs = await api<{ id: string; substation_id: string }[]>(request, token, "/assets/circuits?region=central");
  await page.goto(`/network?region=central&sub=${cs[0].substation_id}&circuit=${cs[0].id}`);
  await expect(page.getByText("Equipment on this circuit")).toBeVisible();
  await page.getByRole("button", { name: "Whole territory" }).click();
  await page.getByRole("row", { name: /^Northeast/ }).click();
  await expect(page).toHaveURL(/region=northeast$/);
  await expect(page.getByText("Equipment on this circuit")).toHaveCount(0);
});

test("6. light and dark themes on the main screens", async ({ page, request }) => {
  const token = await signIn(page, request);
  const ev = await current(request, token);
  const [unit] = await api<Unit[]>(request, token, "/assets/top?kind=power_transformer&n=1");
  const errors = watchErrors(page);
  await page.goto("/");
  const html = page.locator("html");
  const first = await html.getAttribute("data-mantine-color-scheme");
  for (const scheme of ["a", "b"]) {
    if (scheme === "b") {
      await page.getByRole("button", { name: "Toggle colour scheme" }).click();
      await expect(html).not.toHaveAttribute("data-mantine-color-scheme", first!);
    }
    const now = await html.getAttribute("data-mantine-color-scheme");
    for (const [name, path] of [["overview", "/"], ["network", "/network?region=central"], ["assets", "/asset-health"], ["asset", `/asset/${unit.id}`],
      ["event", `/events/${ev.id}?tab=prediction`]]) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      await page.waitForTimeout(800);
      await expect(html).toHaveAttribute("data-mantine-color-scheme", now!);  // preference survives navigation and reloads
      await page.screenshot({ path: `e2e-screens/themes/${now}-${name}.png`, fullPage: false });
    }
  }
  expect(errors).toEqual([]);
});

test("7. existing screens and workflows still work", async ({ page, request, browser }) => {
  const token = await signIn(page, request);
  const ev = await current(request, token);
  const errors = watchErrors(page);
  const routes: [string, RegExp][] = [["/", /Central Oklahoma Tornado Outbreak/], ["/events", /Storm events/], [`/events/${ev.id}`, /EF rating/],
    [`/events/${ev.id}?tab=prediction`, /Predicted peak/], [`/events/${ev.id}?tab=timeline`, /created|prediction/i], ["/outages", /Outages/],
    ["/restoration", /Restoration/], ["/crews", /Crews/], ["/communications", /Communications/], ["/jarvis", /AI Assistant|Jarvis/],
    ["/reports", /Reports/], ["/network", /Network explorer/], ["/asset-health", /Asset health/]];
  for (const [path, text] of routes) {
    await page.goto(path);
    await expect(page.getByText(text).first(), path).toBeVisible();
  }
  // Administration is for administrators: the operations manager is sent back to the overview …
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/$/);
  for (const tab of ["Substation transformers", "By equipment type", "Replacement plan", "Work orders", "Health model"]) {
    await page.goto("/asset-health");
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tabpanel")).toBeVisible();
  }
  await expect(page.getByText("How the health score works")).toBeVisible();

  // a what-if scenario on the prediction
  await page.goto(`/events/${ev.id}?tab=prediction`);
  await page.getByText("EF5", { exact: true }).click();
  await page.getByRole("button", { name: "Try scenario" }).click();
  await expect(page.getByText(/Showing an unsaved scenario: EF5/)).toBeVisible();

  // the assistant answers from live data
  await page.goto("/jarvis");
  const box = page.getByPlaceholder("Type your message");
  await box.fill("Which circuits are in the tornado path?");
  await box.press("Enter");
  await expect(page.getByText(/on the forecast damage paths/).first()).toBeVisible();

  // a work order from an asset's recommended actions
  const [unit] = await api<Unit[]>(request, token, "/assets/top?kind=pole&condition=Critical&n=1");
  await page.goto(`/asset/${unit.id}`);
  await page.getByRole("button", { name: "New work order" }).click();
  await page.getByLabel("Title").fill("E2E inspection");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("E2E inspection").first()).toBeVisible();

  // … and an administrator sees it
  const adminCtx = await browser.newContext();
  const adminPage = await adminCtx.newPage();
  await signIn(adminPage, request, { email: "admin@prairieskypower.example", password: "oms360" });
  await adminPage.goto("/admin");
  await expect(adminPage).toHaveURL(/\/admin/);
  await expect(adminPage.getByRole("tab").first()).toBeVisible();
  await adminCtx.close();

  // public outage map (no sign-in)
  await page.goto("/outage-map");
  await expect(page.getByText("Prairie Sky Power").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("8. errors, invalid selections and empty results", async ({ page, request }) => {
  await signIn(page, request);
  await page.goto("/asset/NOPE-404");
  await expect(page.getByText("Couldn't load this page")).toBeVisible();
  await page.goto("/network?region=nowhere");
  await expect(page.getByText("Region not found")).toBeVisible();
  await page.goto("/network?circuit=FDR-ZZZ-99");
  await expect(page.getByText("Circuit not found")).toBeVisible();
  await page.route("**/api/assets/summary**", r => r.fulfill({ status: 500, body: JSON.stringify({ detail: "Simulated outage of the asset service" }), contentType: "application/json" }));
  await page.goto("/asset-health");
  await expect(page.getByText("Couldn't load this page")).toBeVisible();
  await expect(page.getByText("Simulated outage of the asset service")).toBeVisible();
  await page.unroute("**/api/assets/summary**");
  await page.goto("/");
  await expect(page.getByText("Central Oklahoma Tornado Outbreak").first()).toBeVisible();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByPlaceholder(/Ticket, circuit, substation/).fill("zzqqxx");
  await expect(page.getByText(/Nothing found/)).toBeVisible();
});

const VIEWPORTS: [string, number, number][] = [["desktop", 1440, 900], ["tablet", 820, 1180], ["mobile", 390, 844]];

test("9. responsive layouts", async ({ page, request }) => {
  const token = await signIn(page, request);
  const ev = await current(request, token);
  const [unit] = await api<Unit[]>(request, token, "/assets/top?kind=dist_transformer&n=1");
  for (const [name, w, h] of VIEWPORTS) {
    await page.setViewportSize({ width: w, height: h });
    for (const [label, path] of [["overview", "/"], ["network", "/network?region=central"], ["assets", "/asset-health"], ["asset", `/asset/${unit.id}`],
      ["prediction", `/events/${ev.id}?tab=prediction`]] as const) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      await page.waitForTimeout(1000);
      expect(await overflowsX(page), `${name} ${label} scrolls sideways`).toBe(false);
      await page.screenshot({ path: `e2e-screens/responsive/${name}-${label}.png` });
    }
  }
});


