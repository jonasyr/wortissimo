import { expect, test } from "@playwright/test";

/**
 * The whole single-device flow, on an iPad, with two players.
 *
 * This is the mode with no server-side state at all, so an end-to-end pass
 * is the only thing that proves the screens actually hand off correctly.
 */
async function setupSolo(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Auf Papier" }).click();
  await page.getByLabel("Name Spieler 1").fill("Jonas");
  await page.getByLabel("Name Spieler 2").fill("Freundin");
  await page.getByRole("button", { name: "1 Min", exact: true }).click();
  await page.getByRole("button", { name: /Runde starten/ }).click();
  await expect(page.locator(".source-word")).toBeVisible();
}

test("a solo game runs from setup through claiming to a result", async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await setupSolo(page);

  await page.getByRole("button", { name: "Fertig" }).click();

  // Jonas claims two words, then hands over.
  await expect(page.getByRole("heading", { name: "Jonas" })).toBeVisible();
  const words = page.locator(".stack .row button");
  await words.nth(0).click();
  await words.nth(1).click();
  await expect(page.getByText("2 angetippt")).toBeVisible();
  await page.getByRole("button", { name: "Weiter" }).click();

  // Freundin claims one of the same words, so it must score 1 not 2.
  await expect(page.getByRole("heading", { name: "Freundin" })).toBeVisible();
  await page.locator(".stack .row button").nth(0).click();
  await page.getByRole("button", { name: "Auswerten" }).click();

  await expect(page.getByText(/Jonas —/)).toBeVisible();
  await expect(page.getByText(/Freundin —/)).toBeVisible();
});

test("the solo round screen offers no text input", async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await setupSolo(page);
  // The paper is the input; a text box here would defeat the mode.
  await expect(page.locator(".input-bar")).toHaveCount(0);
});

test("solo setup can add and remove players", async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await page.goto("/");
  await page.getByRole("button", { name: "Auf Papier" }).click();
  await expect(page.getByLabel(/^Name Spieler/)).toHaveCount(2);

  await page.getByLabel("Einen Spieler hinzufügen").click();
  await expect(page.getByLabel(/^Name Spieler/)).toHaveCount(3);

  await page.getByLabel("Einen Spieler entfernen").click();
  await expect(page.getByLabel(/^Name Spieler/)).toHaveCount(2);
});

test("blind mode is offered only for the two-device game", async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Sofort/ })).toBeVisible();

  await page.getByRole("button", { name: "Auf Papier" }).click();
  await expect(page.getByRole("button", { name: /Sofort/ })).toHaveCount(0);
});

test("the blind toggle changes the create button flow", async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.goto("/");
  await page.getByRole("button", { name: /Sofort/ }).click();
  await expect(page.getByRole("button", { name: /Blind/ })).toBeVisible();
  await expect(page.getByText(/erst am Rundenende/)).toBeVisible();
});
