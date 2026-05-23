/**
 * Typed node for ``csv_input`` / ``json_input`` palette items.
 *
 * Holds the user's chosen input file path.
 */

import { BaseNode, type NodeCategory, type NodePosition } from "../base_node";

/** ``csv_input`` and ``json_input`` are the same class with a different type. */
export type DataSourceTypeId = "csv_input" | "json_input";

export class DataSourceNode extends BaseNode {
  readonly node_type: DataSourceTypeId;
  readonly category: NodeCategory = "data";
  readonly label: string;

  selected_file: string | null = null;

  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
    type_id: DataSourceTypeId = "csv_input",
  ) {
    super(id, position);
    this.node_type = type_id;
    this.label = type_id === "json_input" ? "JSON Input" : "CSV Input";
    this.apply_config(config);
  }

  apply_config(config: Record<string, unknown>): void {
    const selected_file = config.selected_file;
    this.selected_file =
      typeof selected_file === "string" && selected_file.length > 0
        ? selected_file
        : null;
  }

  emit_config(): Record<string, unknown> {
    return {
      selected_file: this.selected_file,
    };
  }

  validate(): string | null {
    if (this.selected_file === null) {
      return `${this.label} has no input file selected.`;
    }
    return null;
  }

  protected build_data_payload(): Record<string, unknown> {
    return {
      node_type_id: this.node_type,
      label: this.label,
      category: this.category,
      selected_file: this.selected_file,
    };
  }
}

/**
 * Constructor wrapper used by the registry. The ``json_input`` palette
 * entry maps to the same class with a different ``type_id``, so we register
 * one constructor per type id.
 */
export class JSONInputNode extends DataSourceNode {
  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
  ) {
    super(id, config, position, "json_input");
  }
}

export class CSVInputNode extends DataSourceNode {
  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
  ) {
    super(id, config, position, "csv_input");
  }
}
