/**
 * User journey: "I drop a Label Summary node and change its mode."
 */

import { expect, test } from "@playwright/test";

import { dragPaletteEntryToCanvas } from "./utils/dnd";

test("picking full_async on label_summary shows it as the select value", async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "Blank canvas" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  await dragPaletteEntryToCanvas(page, {
    palette_entry_label: "Label-based summary",
    node_type_id: "label_summary",
  });
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
  await page.locator(".react-flow__node").first().click({ force: true });

  const mode_select = page
    .locator("aside")
    .getByText("Mode", { exact: false })
    .first()
    .locator("..")
    .locator("select");
  await expect(mode_select).toBeVisible();
  await mode_select.selectOption("full_async");
  await expect(mode_select).toHaveValue("full_async");
});


