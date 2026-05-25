/**
 * DOM assertions for the three resource nodes
 * (LLMProvider, Taxonomy, Prompts) and the GroupBy data node.
 */

import { describe, expect, it } from "vitest";

import { GroupByNode } from "@/flow_editor/nodes/group_by_node";
import { LLMProviderNode } from "@/flow_editor/nodes/llm_provider_node";
import { PromptsNode } from "@/flow_editor/nodes/prompts_node";
import { TaxonomyNode } from "@/flow_editor/nodes/taxonomy_node";

import { renderForUser } from "../_helpers";

function render(Component: React.ComponentType<any>, data: Record<string, unknown>) {
  const props = {
    id: "n1",
    type: String(data.node_type_id ?? "x"),
    data,
    selected: false,
    isConnectable: true,
    xPos: 0,
    yPos: 0,
    dragging: false,
    zIndex: 0,
  } as Record<string, unknown>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return renderForUser(<Component {...(props as any)} />);
}

describe("LLMProviderNode", () => {
  it("shows resource id, provider, and model summary", () => {
    const { container } = render(LLMProviderNode, {
      node_type_id: "llm_provider",
      label: "LLM: default",
      category: "resource",
      resource_id: "default",
      provider: "openrouter",
      model: "meta-llama/llama-3.1-70b-instruct",
      temperature: 0.25,
    });
    const body = container.textContent ?? "";
    expect(body).toContain("default");
    expect(body).toContain("openrouter");
    expect(body).toContain("meta-llama/llama-3.1-70b-instruct");
    expect(body).toContain("T=0.25");
  });

  it("shows '- no model -' when the model field is empty", () => {
    const { getByText } = render(LLMProviderNode, {
      node_type_id: "llm_provider",
      label: "LLM: default",
      category: "resource",
      resource_id: "default",
      provider: "openrouter",
      model: "",
      temperature: 0,
    });
    expect(getByText(/no model/i)).toBeInTheDocument();
  });
});

describe("TaxonomyNode", () => {
  it("renders the file-path form when taxonomy_id is null", () => {
    const { getByText } = render(TaxonomyNode, {
      node_type_id: "taxonomy",
      label: "Taxonomy",
      category: "resource",
      taxonomy_id: null,
      taxonomy_path: "config/taxonomy.json",
    });
    expect(getByText("config/taxonomy.json")).toBeInTheDocument();
  });

  it("renders the hosted-id form when taxonomy_id is set", () => {
    const { container } = render(TaxonomyNode, {
      node_type_id: "taxonomy",
      label: "Taxonomy",
      category: "resource",
      taxonomy_id: "my_taxonomy",
      taxonomy_path: "",
    });
    const body = container.textContent ?? "";
    expect(body).toContain("Hosted:");
    expect(body).toContain("my_taxonomy");
  });
});

describe("PromptsNode", () => {
  it("renders the prompts file path", () => {
    const { getByText } = render(PromptsNode, {
      node_type_id: "prompts",
      label: "Prompts",
      category: "resource",
      prompts_path: "config/prompts.json",
    });
    expect(getByText("config/prompts.json")).toBeInTheDocument();
  });
});

describe("GroupByNode", () => {
  it("renders the entity and sort columns", () => {
    const { getByText } = render(GroupByNode, {
      node_type_id: "group_by",
      label: "Group By",
      category: "data",
      entity_column: "victim",
      sort_by_column: "index",
      entity_count_estimate: 500,
      avg_documents_per_entity: 3.5,
    });
    expect(getByText(/Entity:/i)).toBeInTheDocument();
    expect(getByText(/victim/)).toBeInTheDocument();
    expect(getByText(/500 entities/i)).toBeInTheDocument();
  });
});
