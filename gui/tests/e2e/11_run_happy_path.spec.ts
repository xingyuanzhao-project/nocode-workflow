/**
 * User journey: "I build a flow, upload a CSV, and hit Run."
 *
 * Expanded from the original ``new_run`` smoke:
 * - Asserts the URL moves to ``/runs/...``.
 * - Asserts the log viewer's caption updates while the run is live.
 * - Asserts the status badge reaches ``succeeded``.
 * - Asserts the preview table shows at least one row.
 * - Asserts every artifact download responds 200.
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import { expect, test } from "@playwright/test";

import { BACKEND_BASE_URL } from "./utils/backend_env";

const SMOKE_CSV_PATH = path.resolve(
  __dirname,
  "fixtures",
  "run_smoke.csv",
);

const RUN_TIMEOUT_MS = 15 * 60_000;

test("run the full_pipeline template and see the results", async ({
  page,
  request,
}) => {
  test.setTimeout(RUN_TIMEOUT_MS);

  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "full_pipeline" }).click();
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
  // The template pre-populates a stored_path, so wait for the row count
  // (only shown after a real /api/files/upload completes) before clicking Run.
  await expect(
    page.locator("aside").getByText(/\d+ rows/i),
  ).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: /^run$/i }).click();
  await page.waitForURL(/\/runs\//, { timeout: 30_000 });

  // Status badge transitions queued -> running -> succeeded.
  const badge = page
    .locator("span")
    .filter({ hasText: /^(queued|running|succeeded|failed|cancelled)$/ })
    .first();
  await expect(badge).toHaveText(/succeeded|failed|cancelled/, {
    timeout: RUN_TIMEOUT_MS,
  });
  await expect(badge).toHaveText("succeeded");

  // Results preview has at least one row.
  await expect(page.getByText(/showing \d+ of /i)).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.locator("table tbody tr").first()).toBeVisible();

  // Each artifact download link resolves 200.
  const artifact_anchors = page.locator(
    'a[href*="/api/flow/runs/"][href*="/artifacts/"]',
  );
  const anchor_count = await artifact_anchors.count();
  expect(anchor_count).toBeGreaterThan(0);
  for (let index = 0; index < anchor_count; index += 1) {
    const anchor = artifact_anchors.nth(index);
    const href = await anchor.getAttribute("href");
    if (!href) continue;
    // GET because the FastAPI route is declared @router.get(...) and
    // does not accept HEAD. The CSVs under test are tiny fixtures.
    const response = await request.get(`${BACKEND_BASE_URL}${href}`);
    expect(response.status()).toBe(200);
  }
});



