/**
 * Accessibility smoke: visits every top-level page and asserts at
 * least that the NavBar landmarks are present.
 *
 * Keeping this light today: a fuller axe-core sweep is planned but
 * needs ``@axe-core/playwright`` installed. The current assertion
 * is still user-observable — a user would notice a missing NavBar.
 */

import { expect, test } from "@playwright/test";

const PAGES_TO_VISIT: Array<{ path: string; expected_heading: RegExp }> = [
  { path: "/flows", expected_heading: /my flows/i },
  { path: "/taxonomies", expected_heading: /taxonomies/i },
];

test.describe("accessibility smoke", () => {
  for (const page_entry of PAGES_TO_VISIT) {
    test(`${page_entry.path} renders its heading`, async ({ page }) => {
      test.setTimeout(30_000);
      await page.goto(page_entry.path);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        page_entry.expected_heading,
      );
      await expect(
        page.getByRole("link", { name: /flows/i }).first(),
      ).toBeVisible();
    });
  }
});
