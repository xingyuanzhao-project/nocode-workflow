/**
 * Global setup for the GUI vitest suite.
 *
 * - Registers ``@testing-library/jest-dom`` matchers.
 * - Polyfills ``ResizeObserver`` and ``IntersectionObserver`` that
 *   React Flow and Radix UI rely on but jsdom does not provide.
 * - Polyfills ``matchMedia`` because some shadcn/Radix components
 *   inspect it at mount time.
 */

import "@testing-library/jest-dom/vitest";

class _NoopObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): ReadonlyArray<unknown> {
    return [];
  }
}

if (typeof globalThis.ResizeObserver === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).ResizeObserver = _NoopObserver;
}

if (typeof globalThis.IntersectionObserver === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).IntersectionObserver = _NoopObserver;
}

if (typeof globalThis.matchMedia === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}
