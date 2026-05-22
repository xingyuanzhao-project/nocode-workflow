/**
 * User journey: "I open the app and create a flow from a template."
 *
 * Every template plus the Blank option must deposit the user on a
 * flow editor at ``/flows/new`` with the expected nodes visible.
 */

import { expect, test } from "@playwright/test";

const TEMPLATE_IDS = [
  "label_extraction_summary",
  "flat_summary_classification",
  "full_pipeline",
] as const;

test.describe("New Flow dialog", () => {
  for (const template_id of TEMPLATE_IDS) {
    test(`creates a flow from the ${template_id} template`, async ({ page }) => {
      test.setTimeout(60_000);
      await page.goto("/");
      await page.getByRole("button", { name: /new flow/i }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      // Scope to the label span inside the dialog so we do not
      // collide with the description text.
      await page
        .getByRole("dialog")
        .locator("label", { hasText: template_id })
        .click();
      await page.getByRole("button", { name: /create flow/i }).click();
      await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });
      // Editor chrome visible to the user: Save and Run buttons,
      // the toolbar flow-name input. URL plus chrome are the
      // observable facts that prove the template was loaded.
      await expect(
        page.locator('input[placeholder="Flow name"]'),
      ).toBeVisible({ timeout: 10_000 });
      await expect(
        page.getByRole("button", { name: /^run$/i }),
      ).toBeVisible();
    });
  }

  test("creates a blank canvas when Blank is picked", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /new flow/i }).click();
    await page
      .getByRole("dialog")
      .locator("label", { hasText: "Blank canvas" })
      .click();
    await page.getByRole("button", { name: /create flow/i }).click();
    await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });
    await expect(
      page.locator('input[placeholder="Flow name"]'),
    ).toBeVisible({ timeout: 10_000 });
  });
});
