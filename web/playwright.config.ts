import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  // devices["iPhone 14"] selects WebKit, which is the engine iOS Safari
  // actually runs. Testing these behaviours in Chromium would prove very
  // little: the viewport, keyboard and input-zoom rules being verified
  // here are WebKit-specific.
  use: {
    baseURL: process.env.WORTISSIMO_URL ?? "http://127.0.0.1:8000",
    ...devices["iPhone 14"],
  },
});
