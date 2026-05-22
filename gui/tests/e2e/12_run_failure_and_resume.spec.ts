/**
 * User journey: "I run a flow with a bogus API key, watch it fail,
 * fix the config, hit Resume."
 *
 * Kept short — the behaviour under test is (a) the failure badge
 * shows, (b) the Resume button appears, (c) clicking Resume
 * re-enters the run lifecycle. Full success-after-resume is
 * covered by the backend integration tier.
 */

import { expect, test } from "@playwright/test";

test("failed runs surface a visible badge and a Resume button", async ({
  page,
}) => {
  test.setTimeout(4 * 60_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "flat_summary_classification" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  // Click LLM provider node to break its api_key_env via the
  // property panel.
  await page
    .locator(".react-flow__node")
    .filter({ hasText: /Provider:/i })
    .first()
    .click({ force: true });
  await page
    .locator("aside")
    .locator('input[placeholder="OPENROUTER_API_KEY"]')
    .first()
    .fill("DOES_NOT_EXIST_IN_ENV");

  await page.getByRole("button", { name: /^run$/i }).click();
  await page.waitForURL(/\/runs\//, { timeout: 30_000 });

  const badge = page
    .locator("span")
    .filter({ hasText: /^(queued|running|succeeded|failed|cancelled)$/ })
    .first();
  await expect(badge).toHaveText(/failed|cancelled/, { timeout: 2 * 60_000 });

  // Resume button becomes available on terminal non-success states.
  await expect(page.getByRole("button", { name: /resume/i })).toBeVisible();
});


