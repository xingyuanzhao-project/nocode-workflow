/**
 * User journey: "I drop a CSV input, upload a file, map columns."
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import { expect, test } from "@playwright/test";

import { dragPaletteEntryToCanvas } from "./utils/dnd";

const SMOKE_CSV_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "data",
  "df_text_by_report.csv",
);

test("upload a CSV and map the four column roles", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "Blank canvas" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  await dragPaletteEntryToCanvas(page, {
    palette_entry_label: "CSV input table",
    node_type_id: "csv_input",
  });
  await expect(page.locator(".react-flow__node")).toHaveCount(1, {
    timeout: 10_000,
  });

  // Click the canvas node to open its property panel. React Flow
  // wraps the node in a transformed container; ``force: true``
  // bypasses the intersection check that Playwright would otherwise
  // fail when the background pane covers the target.
  await page.locator(".react-flow__node").first().click({ force: true });

  const csv_input_field = page
    .locator('input[type="file"][accept*="csv"]')
    .first();
  await csv_input_field.setInputFiles(SMOKE_CSV_PATH);

  await expect(
    page.locator("aside").getByText(/df_text_by_report\.csv/i),
  ).toBeVisible({ timeout: 30_000 });

  // Property panel exposes four selects for the required roles.
  const role_selects = page.locator("aside select");
  await expect(role_selects).toHaveCount(4);
});



