/**
 * HTML5 drag-and-drop helper for Playwright specs.
 *
 * Playwright's ``locator.dragTo`` does not populate
 * :class:`DataTransfer`, so the palette-to-canvas drag in React Flow
 * would silently drop no node. This helper dispatches real
 * :class:`DragEvent` instances with a real :class:`DataTransfer`
 * through ``page.evaluate`` — the same sequence a human mouse
 * produces.
 *
 * Every palette drag in the e2e suite uses this helper. It is the
 * only place ``page.evaluate`` is allowed to execute JavaScript in
 * the page context.
 */

import type { Page } from "@playwright/test";

/** MIME type the canvas's drop handler reads from ``DataTransfer``. */
export const NODE_TYPE_DRAG_MIME_TYPE = "application/academic_pipeline_node_type";

export interface DragPaletteEntryToCanvasOptions {
  /** Visible label text of the palette button, as a user sees it. */
  palette_entry_label: string;
  /** Node-type id carried in the DataTransfer payload. */
  node_type_id: string;
  /** Selector of the canvas drop zone. */
  canvas_selector?: string;
}

/**
 * Drag a palette entry onto the React Flow canvas.
 *
 * @param page - Playwright page object.
 * @param options - Drag target details.
 * @returns Promise resolved after the ``drop`` event was dispatched.
 */
export async function dragPaletteEntryToCanvas(
  page: Page,
  options: DragPaletteEntryToCanvasOptions,
): Promise<void> {
  const canvas_selector = options.canvas_selector ?? ".react-flow__pane";
  const source_locator = page.getByRole("button", {
    name: options.palette_entry_label,
  });
  await source_locator.scrollIntoViewIfNeeded();
  const source_box = await source_locator.boundingBox();
  if (!source_box) {
    throw new Error(
      `Palette entry '${options.palette_entry_label}' has no bounding box`,
    );
  }
  const canvas_box = await page.locator(canvas_selector).boundingBox();
  if (!canvas_box) {
    throw new Error(`Canvas '${canvas_selector}' has no bounding box`);
  }

  await page.evaluate(
    ({ source_x, source_y, target_x, target_y, mime, payload, canvas }) => {
      const data_transfer = new DataTransfer();
      data_transfer.setData(mime, payload);
      const source_element = document.elementFromPoint(source_x, source_y);
      const target_element = document.querySelector(canvas);
      if (!source_element || !target_element) {
        throw new Error(
          "drag endpoints not present in the DOM at the requested coordinates",
        );
      }
      const dispatch_drag = (
        type: "dragstart" | "dragover" | "drop" | "dragend",
        client_x: number,
        client_y: number,
        element: Element,
      ): void => {
        const event = new DragEvent(type, {
          bubbles: true,
          cancelable: true,
          clientX: client_x,
          clientY: client_y,
          dataTransfer: data_transfer,
        });
        element.dispatchEvent(event);
      };
      dispatch_drag("dragstart", source_x, source_y, source_element);
      dispatch_drag("dragover", target_x, target_y, target_element);
      dispatch_drag("drop", target_x, target_y, target_element);
      dispatch_drag("dragend", target_x, target_y, source_element);
    },
    {
      source_x: source_box.x + source_box.width / 2,
      source_y: source_box.y + source_box.height / 2,
      target_x: canvas_box.x + canvas_box.width / 2,
      target_y: canvas_box.y + canvas_box.height / 2,
      mime: NODE_TYPE_DRAG_MIME_TYPE,
      payload: options.node_type_id,
      canvas: canvas_selector,
    },
  );
}
