/**
 * Canvas node for the taxonomy resource reference.
 *
 * In local-file mode the node carries a project-root-relative POSIX
 * path (``config/taxonomy.json``). Hosted mode (``taxonomy://<id>``)
 * is reserved for the future; the node data already holds the
 * optional ``taxonomy_id`` field so the codec knows which form to
 * emit.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface TaxonomyNodeData {
  node_type_id: "taxonomy";
  label: string;
  category: "resource";
  /** Saved taxonomy id (hosted mode) or ``null`` when using a file. */
  taxonomy_id: string | null;
  /** Local-file path (used when ``taxonomy_id`` is ``null``). */
  taxonomy_path: string;
}

export function TaxonomyNode({
  data,
  selected,
}: NodeProps<TaxonomyNodeData>): JSX.Element {
  return (
    <NodeCard
      category="Resource"
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
      has_input_handle={false}
    >
      <div className="flex flex-col gap-0.5">
        {data.taxonomy_id ? (
          <span>
            Hosted: <span className="font-mono">{data.taxonomy_id}</span>
          </span>
        ) : (
          <span
            className="truncate font-mono"
            title={data.taxonomy_path}
          >
            {data.taxonomy_path || "— path unset —"}
          </span>
        )}
      </div>
    </NodeCard>
  );
}
