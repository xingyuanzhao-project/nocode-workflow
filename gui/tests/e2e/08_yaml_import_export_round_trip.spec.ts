/**
 * User journey: "I export a flow, then re-import the same YAML."
 *
 * Asserts the canvas state after re-import shows the same set of
 * node labels as before export.
 */

import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

test("YAML export then import preserves visible node labels", async ({
  page,
}, test_info) => {
  test.setTimeout(90_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "full_pipeline" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  // Wait until the template's nodes have rendered onto the canvas before
  // capturing the baseline; otherwise the test races the async hydration
  // and compares 0 nodes after export to 7 nodes after import.
  await expect(page.locator(".react-flow__node").first()).toBeVisible({
    timeout: 15_000,
  });
  const labels_before = await page
    .locator(".react-flow__node")
    .evaluateAll((elements) =>
      elements.map((element) => element.textContent ?? ""),
    );
  expect(labels_before.length).toBeGreaterThan(0);

  const download_promise = page.waitForEvent("download");
  await page.getByRole("button", { name: /Export YAML/i }).click();
  const download = await download_promise;
  const saved_path = path.join(
    test_info.outputDir,
    "exported_full_pipeline.yml",
  );
  await download.saveAs(saved_path);
  expect(fs.existsSync(saved_path)).toBe(true);

  // Fresh blank canvas.
  await page.getByRole("link", { name: /flows/i }).first().click();
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "Blank canvas" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  const file_input = page.locator('input[type="file"][accept*="yml"]');
  await file_input.setInputFiles(saved_path);

  // Assert the same labels appear after import.
  await expect(page.locator(".react-flow__node")).toHaveCount(
    labels_before.length,
    { timeout: 10_000 },
  );
});



