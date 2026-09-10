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

test("user chat composer remains visible while messages scroll internally", async ({ page, request }) => {
  const email = `composer-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  const registered = await request.post("/api/auth/register", { data: {
    email, name: "Pengguna Composer", password: "Password123!", device_name: "Browser Device",
    os: "Playwright", agent_version: "1.0.0"
  }});
  expect(registered.ok()).toBeTruthy();
  const user = await registered.json();
  await page.goto("/login.html");
  await page.evaluate(({ token }) => {
    localStorage.setItem("beresin_token", token);
    localStorage.setItem("beresin_user", JSON.stringify({ role: "USER", name: "Pengguna Composer" }));
  }, { token: user.token });
  await page.goto("/index.html");
  await page.evaluate(() => {
    document.querySelector("#empty-state").hidden = true;
    const messages = document.querySelector("#chat-messages");
    const composer = document.querySelector("#chat-composer");
    messages.hidden = false;
    composer.hidden = false;
    for (let index = 0; index < 40; index += 1) {
      const message = document.createElement("div");
      message.className = "message message--assistant";
      message.textContent = `Pesan pengujian ${index + 1}`;
      messages.appendChild(message);
    }
  });
  const layout = await page.evaluate(() => {
    const composer = document.querySelector("#chat-composer").getBoundingClientRect();
    const messages = document.querySelector("#chat-messages");
    return {
      composerTop: composer.top,
      composerBottom: composer.bottom,
      viewportHeight: window.innerHeight,
      pageOverflow: document.documentElement.scrollHeight - window.innerHeight,
      messagesScrollable: messages.scrollHeight > messages.clientHeight,
    };
  });
  expect(layout.composerTop).toBeGreaterThanOrEqual(0);
  expect(layout.composerBottom).toBeLessThanOrEqual(layout.viewportHeight + 1);
  expect(layout.pageOverflow).toBeLessThanOrEqual(1);
  expect(layout.messagesScrollable).toBeTruthy();
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

  await page.goto("/supervisor/operations.html");
  await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
  await expect(page.locator("#ops-status")).not.toHaveText("-");
  await expect(page.locator("#ops-agents .ops-agent-card")).toHaveCount(4);
  result = await new AxeBuilder({ page }).analyze();
  expect(result.violations.filter((item) => ["serious", "critical"].includes(item.impact))).toEqual([]);
});

test("operations owner reviews and re-authenticates an approval", async ({ page, request }) => {
  const supervisorLogin = await request.post("/api/auth/login", { data: {
    email: "supervisor@beresin.example.com", password: "Supervisor123!"
  }});
  expect(supervisorLogin.ok()).toBeTruthy();
  const supervisor = await supervisorLogin.json();
  const headers = { Authorization: `Bearer ${supervisor.token}` };
  const signal = await request.post("/api/internal/ops/signals", {
    headers: { Authorization: "Bearer mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm" },
    data: { source: "ui-owner-drill", title: "Synthetic approval drill", severity: "HIGH", resource: "ui-test" }
  });
  expect(signal.ok()).toBeTruthy();
  const incident = await signal.json();
  const proposal = await request.post(`/api/supervisor/ops/incidents/${incident.id}/proposals`, {
    headers,
    data: { action_type: "CODE_FIX", title: "Review synthetic patch", description: "No production mutation", risk: "Low" }
  });
  expect(proposal.ok()).toBeTruthy();
  const approval = await proposal.json();

  await page.goto("/login.html");
  await page.evaluate(({ token }) => {
    localStorage.setItem("beresin_token", token);
    localStorage.setItem("beresin_user", JSON.stringify({ role: "SUPERVISOR", name: "Supervisor BERESIN" }));
  }, { token: supervisor.token });
  await page.goto("/supervisor/operations.html");
  const approvalCard = page.locator("#ops-approvals .approval-item", { hasText: `Approval #${approval.approval_id}` });
  await expect(approvalCard).toHaveCount(1);
  page.once("dialog", (dialog) => dialog.accept("Supervisor123!"));
  await approvalCard.getByRole("button", { name: "Approve" }).click();
  await expect(approvalCard).toHaveCount(0);
  const approvals = await request.get("/api/supervisor/ops/approvals", { headers });
  expect(approvals.ok()).toBeTruthy();
  const stored = (await approvals.json()).find((item) => item.id === approval.approval_id);
  expect(stored.status).toBe("APPROVED");
});
