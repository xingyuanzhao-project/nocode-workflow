/**
 * TanStack Query hook fetching the node-type catalog.
 *
 * The catalog is used by the palette, the property panel, and the
 * unit-aware edge validator. It is near-static (changes only when
 * ``config/node_types.yaml`` changes on the backend), so the query
 * uses a long stale time so components share one cached copy.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getNodeTypes } from "@/api/schema";
import type { NodeTypeEntry, NodeTypeRegistry } from "@/schemas/node_types";

export const NODE_TYPES_QUERY_KEY = ["node-types"] as const;

/**
 * Return the cached node-type registry, fetching it on first mount.
 */
export function useNodeTypes(): UseQueryResult<NodeTypeRegistry, Error> {
  return useQuery<NodeTypeRegistry, Error>({
    queryKey: NODE_TYPES_QUERY_KEY,
    queryFn: getNodeTypes,
    staleTime: 5 * 60_000,
  });
}

/**
 * Group the registry's entries by :attr:`NodeTypeEntry.category` so
 * the palette can render one section per category without duplicating
 * filtering logic.
 */
export function groupNodeEntriesByCategory(
  registry: NodeTypeRegistry | undefined,
): Record<string, NodeTypeEntry[]> {
  const groups: Record<string, NodeTypeEntry[]> = {};
  if (!registry) {
    return groups;
  }
  for (const entry of registry.entries) {
    const bucket = groups[entry.category] ?? [];
    bucket.push(entry);
    groups[entry.category] = bucket;
  }
  return groups;
}
