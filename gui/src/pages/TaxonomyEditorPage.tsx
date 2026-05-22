/**
 * Taxonomy editor page.
 *
 * Loads one taxonomy by id, renders its labels via
 * :class:`LabelEditor`, and persists changes back to the backend
 * through :func:`updateTaxonomy`.
 */

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { getTaxonomy, updateTaxonomy } from "@/api/taxonomies";
import { Button } from "@/components/ui/button";
import {
  LabelEditor,
  labelEntriesFromJson,
  labelEntriesToJson,
  type LabelEntry,
} from "@/components/LabelEditor";

export default function TaxonomyEditorPage(): JSX.Element {
  const { taxonomy_id } = useParams<{ taxonomy_id: string }>();
  const import_input_ref = useRef<HTMLInputElement | null>(null);

  const [taxonomy_name, set_taxonomy_name] = useState("");
  const [label_entries, set_label_entries] = useState<LabelEntry[]>([]);
  const [is_dirty, set_is_dirty] = useState(false);
  const [editor_error, set_editor_error] = useState<string | null>(null);

  const load_query = useQuery({
    queryKey: ["taxonomy", taxonomy_id],
    queryFn: () => getTaxonomy(taxonomy_id as string),
    enabled: Boolean(taxonomy_id),
  });

  useEffect(() => {
    if (!load_query.data) {
      return;
    }
    set_taxonomy_name(load_query.data.name);
    set_label_entries(labelEntriesFromJson(load_query.data.taxonomy));
    set_is_dirty(false);
  }, [load_query.data]);

  const save_mutation = useMutation({
    mutationFn: () => {
      if (!taxonomy_id) {
        throw new Error("Cannot save: taxonomy id missing from URL");
      }
      return updateTaxonomy(
        taxonomy_id,
        taxonomy_name,
        labelEntriesToJson(label_entries),
      );
    },
    onSuccess: () => {
      set_is_dirty(false);
      set_editor_error(null);
    },
    onError: (caught_error: unknown) => {
      set_editor_error(
        caught_error instanceof Error
          ? caught_error.message
          : String(caught_error),
      );
    },
  });

  const handle_import_json = async (file: File): Promise<void> => {
    try {
      const file_text = await file.text();
      const parsed = JSON.parse(file_text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Imported JSON must be an object keyed by label names.");
      }
      set_label_entries(
        labelEntriesFromJson(parsed as Record<string, unknown>),
      );
      set_is_dirty(true);
      set_editor_error(null);
    } catch (caught_error) {
      set_editor_error(
        caught_error instanceof Error
          ? caught_error.message
          : String(caught_error),
      );
    }
  };

  const handle_export_json = (): void => {
    const blob = new Blob(
      [JSON.stringify(labelEntriesToJson(label_entries), null, 2)],
      { type: "application/json" },
    );
    const object_url = URL.createObjectURL(blob);
    const anchor_element = document.createElement("a");
    anchor_element.href = object_url;
    anchor_element.download = `${taxonomy_name || "taxonomy"}.json`;
    anchor_element.click();
    URL.revokeObjectURL(object_url);
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b px-6 py-3">
        <input
          className="rounded-md border bg-background px-2 py-1 text-sm font-medium min-w-[20rem]"
          value={taxonomy_name}
          onChange={(event) => {
            set_taxonomy_name(event.target.value);
            set_is_dirty(true);
          }}
        />
        <span className="text-xs text-muted-foreground">
          {is_dirty ? "unsaved changes" : "saved"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => import_input_ref.current?.click()}
          >
            Import JSON
          </Button>
          <input
            ref={import_input_ref}
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                void handle_import_json(file);
              }
              event.target.value = "";
            }}
          />
          <Button variant="outline" size="sm" onClick={handle_export_json}>
            Export JSON
          </Button>
          <Button
            size="sm"
            disabled={save_mutation.isPending || !is_dirty}
            onClick={() => save_mutation.mutate()}
          >
            {save_mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </div>
      </header>

      {editor_error ? (
        <div className="border-b bg-destructive/10 px-6 py-2 text-xs text-destructive">
          {editor_error}
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {load_query.isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : load_query.isError ? (
          <div className="text-sm text-destructive">
            Could not load taxonomy: {String(load_query.error)}
          </div>
        ) : (
          <LabelEditor
            entries={label_entries}
            on_change={(next_entries) => {
              set_label_entries(next_entries);
              set_is_dirty(true);
            }}
          />
        )}
      </div>
    </div>
  );
}
