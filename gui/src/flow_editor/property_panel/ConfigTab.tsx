/**
 * Config tab of the :mod:`PropertyPanel`.
 *
 * Dispatches on the selected node's ``node_type_id`` to the right
 * config form. Every form writes its values back to the graph
 * store via :mod:`./node_update_helpers`.
 */

import { DataSourceConfigForm } from "./config_forms/DataSourceConfigForm";
import { LLMProviderConfigForm } from "./config_forms/LLMProviderConfigForm";
import { ProcessingConfigForm } from "./config_forms/ProcessingConfigForm";
import {
  SimpleStringFieldForm,
  type FieldDefinition,
} from "./config_forms/SimpleStringFieldForm";
import type { GraphNode } from "@/stores/graph_store";

const GROUP_BY_FIELDS: readonly FieldDefinition[] = [
  {
    field_name: "entity_column",
    label: "Entity column",
    placeholder: "victim",
    help: "Mirrors column_roles.entity_id on the DataSource.",
  },
  {
    field_name: "sort_by_column",
    label: "Sort-within-entity column",
    placeholder: "index",
    help: "Mirrors column_roles.sort_by on the DataSource.",
  },
];

const TAXONOMY_FIELDS: readonly FieldDefinition[] = [
  {
    field_name: "taxonomy_path",
    label: "Taxonomy file path",
    placeholder: "config/taxonomy.json",
    help: "Project-root-relative POSIX path to the taxonomy JSON.",
  },
  {
    field_name: "taxonomy_id",
    label: "Hosted taxonomy id (optional)",
    nullable: true,
    help: "Leave empty to use the file path above.",
  },
];

const PROMPTS_FIELDS: readonly FieldDefinition[] = [
  {
    field_name: "prompts_path",
    label: "Prompts file path",
    placeholder: "config/prompts.json",
    help: "Project-root-relative POSIX path to the prompts JSON.",
  },
];

const CSV_OUTPUT_FIELDS: readonly FieldDefinition[] = [
  {
    field_name: "summary_csv",
    label: "summary.csv path",
    placeholder: "results/summary.csv",
  },
  {
    field_name: "results_csv",
    label: "results.csv path (optional)",
    nullable: true,
  },
  {
    field_name: "states_csv",
    label: "states.csv path (optional)",
    nullable: true,
  },
  {
    field_name: "spans_csv",
    label: "spans.csv path (optional)",
    nullable: true,
  },
  {
    field_name: "extend",
    label: "Append to existing files (extend)",
    kind: "boolean",
  },
];

export interface ConfigTabProps {
  node: GraphNode;
}

export function ConfigTab({ node }: ConfigTabProps): JSX.Element {
  const node_type_id = String(node.data.node_type_id ?? "");
  const category = String(node.data.category ?? "");

  if (node_type_id === "csv_input") {
    return <DataSourceConfigForm node={node} />;
  }
  if (node_type_id === "group_by") {
    return <SimpleStringFieldForm node={node} fields={GROUP_BY_FIELDS} />;
  }
  if (node_type_id === "llm_provider") {
    return <LLMProviderConfigForm node={node} />;
  }
  if (node_type_id === "taxonomy") {
    return <SimpleStringFieldForm node={node} fields={TAXONOMY_FIELDS} />;
  }
  if (node_type_id === "prompts") {
    return <SimpleStringFieldForm node={node} fields={PROMPTS_FIELDS} />;
  }
  if (node_type_id === "csv_output") {
    return <SimpleStringFieldForm node={node} fields={CSV_OUTPUT_FIELDS} />;
  }
  if (category === "processor") {
    return <ProcessingConfigForm node={node} />;
  }
  return (
    <p className="text-xs text-muted-foreground">
      Node type {node_type_id} has no configuration fields.
    </p>
  );
}
