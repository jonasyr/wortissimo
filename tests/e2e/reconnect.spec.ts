import { expect, test } from "@playwright/test";

/**
 * The scenario no unit test can cover: a real iPhone-sized browser losing
 * its connection mid-round, as happens every time the phone locks.
 *
 * Run against a live server:
 *   WORTISSIMO_URL=https://<host>.ts.net npx playwright test
 */

async function startRound(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("Dein Name").fill("jw");
  await page.getByRole("button", { name: "Neues Spiel" }).click();
  await page.getByRole("button", { name: "Runde starten" }).click();
  await expect(page.locator(".source-word")).toBeVisible();
}

test("a word submitted while offline survives reconnection", async ({
  page,
  context,
}) => {
  await startRound(page);
  const source = (await page.locator(".source-word").innerText()).toLowerCase();

  await context.setOffline(true);
  await page.getByLabel("Gefundenes Wort").fill(source.slice(0, 5));
  await page.getByRole("button", { name: "OK" }).click();
  await context.setOffline(false);

  // The outbox replays on reconnect; the verdict must arrive eventually.
  await expect(page.locator(".chip, .flash")).toHaveCount(1, { timeout: 20_000 });
});

test("the timer recovers after the tab is backgrounded", async ({ page }) => {
  await startRound(page);
  const before = await page.locator(".timer").innerText();

  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await page.waitForTimeout(2000);

  const after = await page.locator(".timer").innerText();
  expect(after).not.toBe(before);
});

test("the input does not zoom the page on focus", async ({ page }) => {
  await startRound(page);
  const size = await page
    .getByLabel("Gefundenes Wort")
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  // Below 16px iOS force-zooms and cannot be zoomed back out.
  expect(size).toBeGreaterThanOrEqual(16);
});
