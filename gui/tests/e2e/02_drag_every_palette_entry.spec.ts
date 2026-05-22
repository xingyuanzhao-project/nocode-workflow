/**
 * User journey: "I drag each palette entry onto a blank canvas."
 *
 * Exercises real HTML5 drag-and-drop via
 * :func:`dragPaletteEntryToCanvas`. Every dropped entry must
 * render a card on the canvas. This spec is the real fix for the
 * DataSource palette-drop crash.
 */

import { expect, test } from "@playwright/test";

import { dragPaletteEntryToCanvas } from "./utils/dnd";

const PALETTE_ENTRIES: Array<{ label: string; node_type_id: string }> = [
  { label: "CSV input table", node_type_id: "csv_input" },
  { label: "Single-document summary", node_type_id: "single_summary" },
  { label: "Conversation summary (first turn)", node_type_id: "conversation_summary_first" },
  { label: "Conversation summary (update turn)", node_type_id: "conversation_summary_update" },
  { label: "Per-label span extraction", node_type_id: "label_extraction" },
  { label: "Label-based summary", node_type_id: "label_summary" },
  { label: "Row-level taxonomy classification", node_type_id: "classification" },
  { label: "LLM provider endpoint", node_type_id: "llm_provider" },
];

test("every palette entry drops onto the canvas without crashing", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "Blank canvas" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  const initial_count = await page.locator(".react-flow__node").count();
  expect(initial_count).toBe(0);

  for (const entry of PALETTE_ENTRIES) {
    await dragPaletteEntryToCanvas(page, {
      palette_entry_label: entry.label,
      node_type_id: entry.node_type_id,
    });
  }

  await expect(page.locator(".react-flow__node")).toHaveCount(
    PALETTE_ENTRIES.length,
    { timeout: 15_000 },
  );
  // No router error-boundary overlay.
  await expect(page.getByText(/Unexpected Application Error/i)).toHaveCount(0);
});


