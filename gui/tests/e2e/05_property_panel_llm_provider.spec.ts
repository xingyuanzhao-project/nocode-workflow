/**
 * User journey: "I click the LLM provider node and switch provider."
 *
 * When the user picks ``openai`` from the provider select, the GUI
 * must fetch ``/api/models/openai``. This spec watches the network.
 */

import { expect, test } from "@playwright/test";

import { dragPaletteEntryToCanvas } from "./utils/dnd";

test("switching provider fires a /api/models request", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto("/");
  await page.getByRole("button", { name: /new flow/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("dialog").locator("label", { hasText: "Blank canvas" }).click();
  await page.getByRole("button", { name: /create flow/i }).click();
  await page.waitForURL(/\/flows\/new/, { timeout: 15_000 });

  await dragPaletteEntryToCanvas(page, {
    palette_entry_label: "LLM provider endpoint",
    node_type_id: "llm_provider",
  });
  await expect(
    page.locator(".react-flow__node").filter({ hasText: /Provider:/i }).first(),
  ).toBeVisible();
  await page
    .locator(".react-flow__node")
    .filter({ hasText: /Provider:/i })
    .first()
    .click({ force: true });

  // Wait for the property panel's provider select to be visible
  // before interacting. The LLMProviderConfigForm renders Provider
  // as the first ``select`` element inside the ``aside`` panel;
  // scoping here avoids matching the node card's "Provider:" label.
  const provider_select = page.locator("aside").locator("select").first();
  await expect(provider_select).toBeVisible();

  const models_response = page.waitForResponse(
    (response) =>
      response.url().includes("/api/models/openai") && response.status() < 500,
    { timeout: 15_000 },
  );
  await provider_select.selectOption("openai");
  await models_response;
});


