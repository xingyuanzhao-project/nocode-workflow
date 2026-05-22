/**
 * User journey: "I start a run, navigate away and back, see the run
 * page again."
 *
 * Pins today's behaviour: after nav-away and back, the log viewer
 * must either reconnect (Streaming caption) or show Finished.
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import { expect, test } from "@playwright/test";

const SMOKE_CSV_PATH = path.resolve(
  __dirname,
  "fixtures",
  "run_smoke.csv",
);

test("navigating away and back lands on a live run page", async ({ page }) => {
  test.setTimeout(10 * 60_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "flat_summary_classification" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  await page
    .locator(".react-flow__node")
    .filter({ hasText: /CSV input/i })
    .first()
    .click({ force: true });
  await page
    .locator("aside")
    .locator('input[type="file"][accept*="csv"]')
    .first()
    .setInputFiles(SMOKE_CSV_PATH);

  await page.getByRole("button", { name: /^run$/i }).click();
  await page.waitForURL(/\/runs\//, { timeout: 30_000 });
  const run_page_url = page.url();

  // Navigate away.
  await page.getByRole("link", { name: /flows/i }).first().click();
  await page.waitForURL(/\/flows$/, { timeout: 15_000 });

  // Navigate back.
  await page.goto(run_page_url);
  await expect(
    page.getByText(/Streaming|Finished \(/).first(),
  ).toBeVisible({ timeout: 60_000 });
});



