/**
 * Config-tab form for the DataSource (CSV input) node.
 *
 * Embeds the :class:`CSVUploader` widget to attach a file and the
 * :class:`ColumnMapper` widget to bind the four required role
 * columns. Changes are written straight through to the graph store.
 */

import { useCallback } from "react";

import { ColumnMapper } from "@/components/ColumnMapper";
import { CSVUploader } from "@/components/CSVUploader";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";
import type { CSVUploadResponse } from "@/schemas/files";
import type { ColumnRoles } from "@/schemas/flow";

export interface DataSourceConfigFormProps {
  node: GraphNode;
}

const INITIAL_COLUMN_ROLES: Partial<ColumnRoles> = {
  text: undefined,
  entity_id: undefined,
  doc_id: undefined,
  sort_by: undefined,
};

function readCurrentUpload(node: GraphNode): CSVUploadResponse | null {
  const upload = node.data.upload;
  return upload && typeof upload === "object"
    ? (upload as CSVUploadResponse)
    : null;
}

function readColumnRoles(node: GraphNode): Partial<ColumnRoles> {
  const roles = node.data.column_roles;
  if (roles && typeof roles === "object" && !Array.isArray(roles)) {
    return { ...INITIAL_COLUMN_ROLES, ...(roles as Partial<ColumnRoles>) };
  }
  return INITIAL_COLUMN_ROLES;
}

export function DataSourceConfigForm({
  node,
}: DataSourceConfigFormProps): JSX.Element {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  const current_upload = readCurrentUpload(node);
  const column_roles = readColumnRoles(node);

  const on_uploaded = useCallback(
    (upload: CSVUploadResponse) => {
      update_node_data(node.id, {
        upload,
      });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const on_role_change = useCallback(
    (role_name: keyof ColumnRoles, column_name: string) => {
      update_node_data(node.id, {
        column_roles: {
          ...column_roles,
          [role_name]: column_name || undefined,
        },
      });
      set_dirty(true);
    },
    [column_roles, node.id, update_node_data, set_dirty],
  );

  return (
    <div className="flex flex-col gap-4">
      <CSVUploader
        current_upload={current_upload}
        on_uploaded={on_uploaded}
      />
      <div>
        <h3 className="mb-1 text-xs font-medium">Column roles</h3>
        <ColumnMapper
          columns={current_upload?.columns ?? []}
          column_roles={column_roles}
          on_change={on_role_change}
        />
      </div>
    </div>
  );
}
