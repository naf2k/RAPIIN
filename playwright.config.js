const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./ui-tests",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8876",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "server/.venv/bin/python server/run.py",
    url: "http://127.0.0.1:8876/health",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      ...process.env,
      BERESIN_HOST: "127.0.0.1",
      BERESIN_PORT: "8876",
      BERESIN_ENV: "test",
      BERESIN_DB_PATH: "/tmp/beresin-playwright.db",
      BERESIN_DATA_DIR: "/tmp/beresin-playwright-data",
      BERESIN_DATABASE_URL: "",
      BERESIN_REDIS_URL: "",
      BERESIN_ALLOW_PUBLIC_REGISTRATION: "true",
      BERESIN_INIT_SUPERVISOR_EMAIL: "supervisor@beresin.example.com",
      BERESIN_INIT_SUPERVISOR_PASSWORD: "Supervisor123!",
      BERESIN_INIT_SUPERVISOR_PASSWORD_FILE: "",
      BERESIN_SECRET_KEY_FILE: "",
      BERESIN_MONITORING_TOKEN_FILE: "",
      BERESIN_MONITORING_TOKEN: "mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm",
      OPS_TELEGRAM_BOT_TOKEN_FILE: "",
      OPS_AGENTS_ENABLED: "false"
    }
  }
});
