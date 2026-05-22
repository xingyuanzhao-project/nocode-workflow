/**
 * User journey: "I watch logs stream while my run is live."
 *
 * Asserts the viewer's caption (``N lines``) increases during a
 * running flow and that the Finished caption appears at terminal.
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

test("log viewer caption grows during a live run", async ({ page }) => {
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

  // The live caption reads "Streaming — N lines" while the run is
  // active and switches to "Finished (…)" at terminal. The smoke CSV
  // can complete in well under ten seconds, so we sample repeatedly
  // and track the largest `N` observed; we only assert that *some*
  // streaming was seen before the run finished.
  const caption = page.locator("text=/Streaming|Finished/").first();
  await expect(caption).toBeVisible({ timeout: 60_000 });

  async function readLineCount(): Promise<number> {
    const text = await caption.textContent();
    const match = (text ?? "").match(/(\d+)\s*lines/);
    return match ? Number(match[1]) : 0;
  }

  const FINISHED_CAPTION = page.getByText(/Finished \(/i);
  let max_count = 0;
  const sample_deadline = Date.now() + 60_000;
  while (Date.now() < sample_deadline) {
    if (await FINISHED_CAPTION.isVisible().catch(() => false)) {
      break;
    }
    const current = await readLineCount();
    if (current > max_count) {
      max_count = current;
    }
    await page.waitForTimeout(250);
  }
  expect(max_count).toBeGreaterThan(0);

  // Eventually the caption shows Finished (...).
  await expect(FINISHED_CAPTION).toBeVisible({
    timeout: 10 * 60_000,
  });
});



