const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

const pages = [
  "/login.html",
  "/states/user-chat-active.html",
  "/states/user-chat-approval.html",
  "/states/user-chat-error.html",
  "/states/user-chat-progress.html",
  "/states/supervisor-overview-empty.html",
  "/states/supervisor-approvals-success.html",
  "/states/supervisor-tasks-loading.html",
];

for (const path of pages) {
  test(`${path} has no serious accessibility violations`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("body")).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    const blocking = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
    expect(blocking, blocking.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
  });
}

test("mobile layouts do not overflow horizontally", async ({ page }) => {
  for (const path of pages) {
    await page.goto(path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(1);
  }
});

test("login is keyboard operable with visible focus", async ({ page }) => {
  await page.goto("/login.html");
  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toBeVisible();
  const outline = await focused.evaluate((element) => getComputedStyle(element).outlineStyle);
  expect(outline).not.toBe("none");
});

test("authenticated user and supervisor pages render live API data accessibly", async ({ page, request }) => {
  const email = `ui-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  const registered = await request.post("/api/auth/register", { data: {
    email, name: "Pengguna UI", password: "Password123!", device_name: "Browser Device",
    os: "Playwright", agent_version: "1.0.0"
  }});
  expect(registered.ok()).toBeTruthy();
  const user = await registered.json();
  await page.goto("/login.html");
  await page.evaluate(({ token }) => {
    localStorage.setItem("beresin_token", token);
    localStorage.setItem("beresin_user", JSON.stringify({ role: "USER", name: "Pengguna UI" }));
  }, { token: user.token });
  await page.goto("/index.html");
  await expect(page.getByRole("heading", { name: "Bagaimana saya dapat membantu?" })).toBeVisible();
  let result = await new AxeBuilder({ page }).analyze();
  expect(result.violations.filter((item) => ["serious", "critical"].includes(item.impact))).toEqual([]);

  const supervisorLogin = await request.post("/api/auth/login", { data: {
    email: "supervisor@beresin.example.com", password: "Supervisor123!"
  }});
  expect(supervisorLogin.ok()).toBeTruthy();
  const supervisor = await supervisorLogin.json();
  await page.evaluate(({ token }) => {
    localStorage.setItem("beresin_token", token);
    localStorage.setItem("beresin_user", JSON.stringify({ role: "SUPERVISOR", name: "Supervisor BERESIN" }));
  }, { token: supervisor.token });
  await page.goto("/supervisor/overview.html");
  await expect(page.locator("#metric-users")).not.toHaveText("-");
  result = await new AxeBuilder({ page }).analyze();
  expect(result.violations.filter((item) => ["serious", "critical"].includes(item.impact))).toEqual([]);
});
