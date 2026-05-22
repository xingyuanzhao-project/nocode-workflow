/**
 * User journey: "I drag three nodes, press Undo, press Redo."
 *
 * Observes only the visible node count and the Undo/Redo button
 * disabled states — no store peeks.
 */

import { expect, test } from "@playwright/test";

import { dragPaletteEntryToCanvas } from "./utils/dnd";

test("Undo reduces node count and disables button when history empty", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "Blank canvas" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  const entries = [
    { label: "CSV input table", node_type_id: "csv_input" },
    { label: "Single-document summary", node_type_id: "single_summary" },
    { label: "LLM provider endpoint", node_type_id: "llm_provider" },
  ];
  for (const entry of entries) {
    await dragPaletteEntryToCanvas(page, {
      palette_entry_label: entry.label,
      node_type_id: entry.node_type_id,
    });
  }
  await expect(page.locator(".react-flow__node")).toHaveCount(3);

  const undo_button = page.getByRole("button", { name: /undo/i }).first();
  const redo_button = page.getByRole("button", { name: /redo/i }).first();

  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (!(await undo_button.isEnabled())) break;
    await undo_button.click();
  }
  await expect(undo_button).toBeDisabled();
  // All three nodes are gone — user sees an empty canvas.
  await expect(page.locator(".react-flow__node")).toHaveCount(0);

  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (!(await redo_button.isEnabled())) break;
    await redo_button.click();
  }
  await expect(redo_button).toBeDisabled();
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
});


