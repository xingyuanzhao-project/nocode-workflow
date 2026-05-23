/**
 * Typed node for the ``codebook`` palette item.
 *
 * The codebook is the taxonomy resource a processor consults via a
 * ``codebook_inquiry`` edge from its bottom handle. Two source kinds:
 *
 * - ``codebook_id`` — server-managed codebook resolved at run time.
 * - ``codebook_path`` — project-root-relative POSIX path to a JSON
 *   taxonomy file on disk.
 *
 * Exactly one of the two should be set; :meth:`validate` enforces that.
 */

import { BaseNode, type NodeCategory, type NodePosition } from "../base_node";

export class CodebookNode extends BaseNode {
  readonly node_type = "codebook";
  readonly category: NodeCategory = "resource";
  readonly label: string = "Codebook";

  codebook_id: string | null = null;
  codebook_path: string | null = null;

  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
  ) {
    super(id, position);
    this.apply_config(config);
  }

  apply_config(config: Record<string, unknown>): void {
    this.codebook_id =
      typeof config.codebook_id === "string" && config.codebook_id.length > 0
        ? config.codebook_id
        : null;
    this.codebook_path =
      typeof config.codebook_path === "string" &&
      config.codebook_path.length > 0
        ? config.codebook_path
        : null;
  }

  emit_config(): Record<string, unknown> {
    return {
      codebook_id: this.codebook_id,
      codebook_path: this.codebook_path,
    };
  }

  validate(): string | null {
    if (this.codebook_id === null && this.codebook_path === null) {
      return `Codebook "${this.id}" has neither codebook_id nor codebook_path set.`;
    }
    if (this.codebook_id !== null && this.codebook_path !== null) {
      return `Codebook "${this.id}" sets both codebook_id and codebook_path; use exactly one.`;
    }
    return null;
  }

  protected build_data_payload(): Record<string, unknown> {
    return {
      node_type_id: this.node_type,
      label: this.label,
      category: this.category,
      codebook_id: this.codebook_id,
      codebook_path: this.codebook_path,
      taxonomy_id: this.codebook_id,
      taxonomy_path: this.codebook_path ?? "",
    };
  }
}
