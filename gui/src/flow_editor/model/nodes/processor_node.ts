/**
 * Typed node for the ``processor`` palette item.
 *
 * One processor is one step in the LLM pipeline: it consumes upstream
 * data via its left handle, optionally calls an LLM through its top
 * handle, optionally consults a codebook through its bottom handle, and
 * emits results to whatever feedforward edge leaves its right handle.
 *
 * The processor's configuration carries:
 *
 * - ``unit`` — granularity of the input (``row``, ``document``,
 *   ``entity``); validated by :data:`VALID_ADJACENT_UNIT_TRANSITIONS`.
 * - ``group_by`` — optional grouping column, mainly used for the
 *   ``document`` and ``entity`` units.
 * - ``prompt`` — inline prompt instructions sent as the system prompt.
 * - ``prompts_ref`` — alternative pointer to a shared prompt template.
 * - ``io_schema`` — output field shape the LLM is expected to return.
 */

import { BaseNode, type NodeCategory, type NodePosition } from "../base_node";

export type UnitValue = "row" | "document" | "entity";

const ALLOWED_UNITS: ReadonlySet<UnitValue> = new Set(["row", "document", "entity"]);

/** Inline prompt block. Mirrors :class:`src.prompt_resolver.PromptInline`. */
export interface PromptInline {
  instructions: string[];
  output_format?: Record<string, unknown> | null;
}

/** Output schema block. Mirrors the ``io_schema:`` YAML field. */
export interface IOSchemaBlock {
  input?: Record<string, unknown>;
  output: Record<string, unknown>;
  required_output?: string[];
}

const DEFAULT_IO_SCHEMA: IOSchemaBlock = { output: {} };

export class ProcessorNode extends BaseNode {
  readonly node_type = "processor";
  readonly category: NodeCategory = "processor";
  readonly label: string = "Processor";

  unit: UnitValue = "row";
  group_by: string | null = null;
  prompt: PromptInline | null = { instructions: [] };
  prompts_ref: string | null = null;
  prompt_overrides: Record<string, unknown> | null = null;
  io_schema: IOSchemaBlock = { ...DEFAULT_IO_SCHEMA };
  mode: string | null = null;
  keys: unknown = null;

  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
  ) {
    super(id, position);
    this.apply_config(config);
  }

  apply_config(config: Record<string, unknown>): void {
    const unit_value = config.unit;
    this.unit =
      typeof unit_value === "string" && ALLOWED_UNITS.has(unit_value as UnitValue)
        ? (unit_value as UnitValue)
        : "row";

    const group_by = config.group_by;
    this.group_by =
      typeof group_by === "string" && group_by.length > 0 ? group_by : null;

    const prompt = config.prompt;
    if (prompt && typeof prompt === "object") {
      const incoming = prompt as Record<string, unknown>;
      const instructions = Array.isArray(incoming.instructions)
        ? incoming.instructions.map(String)
        : [];
      const output_format =
        incoming.output_format && typeof incoming.output_format === "object"
          ? (incoming.output_format as Record<string, unknown>)
          : null;
      this.prompt = { instructions, output_format };
    } else {
      this.prompt = prompt === null ? null : { instructions: [] };
    }

    this.prompts_ref =
      typeof config.prompts_ref === "string" && config.prompts_ref.length > 0
        ? config.prompts_ref
        : null;
    this.prompt_overrides =
      config.prompt_overrides && typeof config.prompt_overrides === "object"
        ? (config.prompt_overrides as Record<string, unknown>)
        : null;

    const io_schema = config.io_schema;
    if (io_schema && typeof io_schema === "object") {
      const incoming = io_schema as Record<string, unknown>;
      const output_block =
        incoming.output && typeof incoming.output === "object"
          ? (incoming.output as Record<string, unknown>)
          : {};
      const input_block =
        incoming.input && typeof incoming.input === "object"
          ? (incoming.input as Record<string, unknown>)
          : undefined;
      const required_output = Array.isArray(incoming.required_output)
        ? incoming.required_output.map(String)
        : undefined;
      this.io_schema = {
        ...(input_block ? { input: input_block } : {}),
        output: output_block,
        ...(required_output ? { required_output } : {}),
      };
    } else {
      this.io_schema = { ...DEFAULT_IO_SCHEMA };
    }

    this.mode = typeof config.mode === "string" ? config.mode : null;
    this.keys = config.keys ?? null;
  }

  emit_config(): Record<string, unknown> {
    const out: Record<string, unknown> = {
      unit: this.unit,
      group_by: this.group_by,
      io_schema: this.io_schema,
    };
    if (this.prompt !== null) {
      out.prompt = this.prompt;
    } else {
      out.prompt = null;
    }
    if (this.prompts_ref !== null) {
      out.prompts_ref = this.prompts_ref;
    }
    if (this.prompt_overrides !== null) {
      out.prompt_overrides = this.prompt_overrides;
    }
    if (this.mode !== null) {
      out.mode = this.mode;
    }
    if (this.keys !== null) {
      out.keys = this.keys;
    }
    return out;
  }

  validate(): string | null {
    const has_inline_prompt =
      this.prompt !== null &&
      Array.isArray(this.prompt.instructions) &&
      this.prompt.instructions.length > 0;
    const has_prompt_ref = this.prompts_ref !== null;
    if (!has_inline_prompt && !has_prompt_ref) {
      return `Processor "${this.id}" has no prompt instructions or prompts_ref.`;
    }
    if (this.prompt !== null && this.prompts_ref !== null) {
      return `Processor "${this.id}" sets both inline prompt and prompts_ref; use exactly one.`;
    }
    const output_keys = Object.keys(this.io_schema.output ?? {});
    if (output_keys.length === 0) {
      return `Processor "${this.id}" has no output fields defined in io_schema.output.`;
    }
    return null;
  }

  protected build_data_payload(): Record<string, unknown> {
    return {
      node_type_id: this.node_type,
      label: this.label,
      category: this.category,
      unit: this.unit,
      group_by: this.group_by,
      prompt: this.prompt,
      prompts_ref: this.prompts_ref,
      prompt_overrides: this.prompt_overrides,
      io_schema: this.io_schema,
      mode: this.mode,
      keys: this.keys,
    };
  }
}

/**
 * Allowed ``(previous_unit, current_unit)`` pairs between adjacent
 * processors. Mirrors :data:`src.flow_loader.VALID_ADJACENT_UNIT_TRANSITIONS`
 * and the existing :data:`@/lib/unit_compatibility.VALID_ADJACENT_UNIT_TRANSITIONS`.
 */
export const VALID_ADJACENT_UNIT_TRANSITIONS: ReadonlyArray<
  readonly [UnitValue, UnitValue]
> = [
  ["row", "row"],
  ["document", "document"],
  ["document", "entity"],
  ["entity", "entity"],
] as const;

export function is_valid_unit_transition(
  previous_unit: UnitValue,
  current_unit: UnitValue,
): boolean {
  return VALID_ADJACENT_UNIT_TRANSITIONS.some(
    ([from_unit, to_unit]) =>
      from_unit === previous_unit && to_unit === current_unit,
  );
}
