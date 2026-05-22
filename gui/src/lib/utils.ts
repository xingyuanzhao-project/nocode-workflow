/**
 * Utility helpers shared across shadcn/ui components and domain code.
 *
 * `cn` is the class-merging helper every shadcn/ui component expects
 * (`import { cn } from "@/lib/utils"`).
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combine Tailwind class strings, deduplicating conflicting utilities.
 *
 * @param inputs - Any number of class values, in the shape accepted by clsx.
 * @returns One merged class string suitable for `className`.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
