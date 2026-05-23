/**
 * Typed node for ``csv_output`` / ``json_output`` palette items.
 *
 * Holds the on-disk output path, output field names, and the
 * ``extend`` flag (``true`` = append to existing file, ``false`` =
 * overwrite).
 */

import { BaseNode, type NodeCategory, type NodePosition } from "../base_node";

export type OutputTypeId = "csv_output" | "json_output";

export class OutputNode extends BaseNode {
  readonly node_type: OutputTypeId;
  readonly category: NodeCategory = "data";
  readonly label: string;

  output_path: string = "results/output.csv";
  extend: boolean = false;
  output_fields: string[] = ["summary"];

  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
    type_id: OutputTypeId = "csv_output",
  ) {
    super(id, position);
    this.node_type = type_id;
    this.label = type_id === "json_output" ? "JSON Output" : "CSV Output";
    this.apply_config(config);
  }

  apply_config(config: Record<string, unknown>): void {
    this.output_path =
      typeof config.output_path === "string"
        ? config.output_path
        : "results/output.csv";
    this.extend = config.extend === true;
    this.output_fields = Array.isArray(config.output_fields)
      ? config.output_fields.map(String).filter(Boolean)
      : ["summary"];
  }

  emit_config(): Record<string, unknown> {
    return {
      output_path: this.output_path,
      extend: this.extend,
      output_fields: [...this.output_fields],
    };
  }

  validate(): string | null {
    if (!this.output_path || this.output_path.trim().length === 0) {
      return `${this.label} has no output path set.`;
    }
    return null;
  }

  protected build_data_payload(): Record<string, unknown> {
    return {
      node_type_id: this.node_type,
      label: this.label,
      category: this.category,
      output_path: this.output_path,
      extend: this.extend,
      output_fields: [...this.output_fields],
    };
  }
}

export class CSVOutputNode extends OutputNode {
  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
  ) {
    super(id, config, position, "csv_output");
  }
}

export class JSONOutputNode extends OutputNode {
  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
  ) {
    super(id, config, position, "json_output");
  }
}
