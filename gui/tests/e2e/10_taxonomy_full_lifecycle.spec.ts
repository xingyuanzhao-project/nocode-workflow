/**
 * User journey: "I open the Taxonomies page, create a taxonomy,
 * add labels, save, delete."
 */

import { expect, test } from "@playwright/test";

test("taxonomy CRUD through the GUI", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto("/taxonomies");

  const unique_name = `e2e taxonomy ${Date.now()}`;
  await page.locator('input[placeholder="New taxonomy name"]').fill(unique_name);
  await page.getByRole("button", { name: /create/i }).click();

  await page.waitForURL(/\/taxonomies\/.+/, { timeout: 15_000 });

  await page.getByRole("button", { name: /add label/i }).click();
  await expect(page.getByText(/Definition/i).first()).toBeVisible();

  await page.getByRole("button", { name: /^save$/i }).click();
  await expect(page.getByText(/saved/i).first()).toBeVisible();

  await page.getByRole("link", { name: /Taxonomies/i }).first().click();
  await expect(page.getByText(unique_name)).toBeVisible();

  const row = page.locator("tr", { hasText: unique_name });
  page.once("dialog", (dialog) => dialog.accept());
  await row.getByRole("button", { name: /delete/i }).click();
  await expect(page.getByText(unique_name)).toHaveCount(0, { timeout: 10_000 });
});
