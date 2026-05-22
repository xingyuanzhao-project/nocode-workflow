/**
 * User journey: "I save a flow, open it, duplicate, delete."
 */

import { expect, test } from "@playwright/test";

test("save, open, duplicate, delete flow lifecycle", async ({ page }) => {
  test.setTimeout(60_000);
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "full_pipeline" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  const unique_flow_name = `e2e flow ${Date.now()}`;
  const name_input = page.locator('input[placeholder="Flow name"]');
  await name_input.fill(unique_flow_name);
  await page.getByRole("button", { name: /save new/i }).click();
  await page.waitForURL(/\/flows\/.+\/edit/, { timeout: 15_000 });
  await expect(page.getByText("saved")).toBeVisible();

  // Navigate to My Flows and assert the flow is listed.
  await page.getByRole("link", { name: /flows/i }).first().click();
  await expect(page.getByText(unique_flow_name)).toBeVisible();

  // Duplicate.
  const row = page.locator("tr", { hasText: unique_flow_name });
  await row.getByRole("button", { name: /duplicate/i }).click();
  await expect(page.getByText(`${unique_flow_name} (copy)`)).toBeVisible({
    timeout: 10_000,
  });

  // Delete both.
  for (const rendered_name of [
    `${unique_flow_name} (copy)`,
    unique_flow_name,
  ]) {
    const row_to_delete = page.locator("tr", { hasText: rendered_name });
    await row_to_delete.getByRole("button", { name: /delete/i }).click();
    await expect(page.getByText(rendered_name)).toHaveCount(0, {
      timeout: 10_000,
    });
  }
});


