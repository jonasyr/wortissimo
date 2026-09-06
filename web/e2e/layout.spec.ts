import { devices, expect, test } from "@playwright/test";

/**
 * Layout checks at real device sizes.
 *
 * The failure these guard against is silent: a page that renders fine on a
 * phone and sprawls edge-to-edge on an iPad, or a body that scrolls
 * sideways because one element overflows.
 */
const SIZES = [
  { name: "iPhone SE", width: 375, height: 667 },
  { name: "iPhone 14 Pro Max", width: 430, height: 932 },
  { name: "iPad mini portrait", width: 744, height: 1133 },
  { name: "iPad Pro 11 portrait", width: 834, height: 1194 },
  { name: "iPad Pro 12.9 landscape", width: 1366, height: 1024 },
];

for (const size of SIZES) {
  test(`lobby fits ${size.name} without sideways scroll`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto("/");
    await expect(page.getByLabel("Dein Name")).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, "page scrolls horizontally").toBeLessThanOrEqual(1);
  });

  test(`content stays readable-width on ${size.name}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto("/");
    const box = await page.locator(".stack").boundingBox();
    expect(box).not.toBeNull();
    // Never wider than the reading measure, never narrower than the screen
    // minus its padding.
    expect(box!.width).toBeLessThanOrEqual(690);
  });
}

test("round screen keeps the input reachable on a tall iPad", async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await page.goto("/");
  await page.getByLabel("Dein Name").fill("jw");
  await page.getByRole("button", { name: /Neues Spiel/ }).click();
  await page.getByRole("button", { name: "Runde starten" }).click();

  const input = page.getByLabel("Gefundenes Wort");
  await expect(input).toBeVisible();

  const box = await input.boundingBox();
  expect(box).not.toBeNull();
  // Inside the viewport, not off the bottom edge.
  expect(box!.y + box!.height).toBeLessThanOrEqual(1194);
  // And not stretched the full 834pt width.
  expect(box!.width).toBeLessThanOrEqual(690);
});

test("the source word does not overflow its container", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await page.getByLabel("Dein Name").fill("jw");
  await page.getByRole("button", { name: /Neues Spiel/ }).click();
  await page.getByRole("button", { name: "Runde starten" }).click();

  const word = page.locator(".source-word");
  await expect(word).toBeVisible();
  const overflow = await word.evaluate(
    (el) => el.scrollWidth - el.clientWidth,
  );
  expect(overflow, "long compound overflows on a narrow phone").toBeLessThanOrEqual(1);
});
