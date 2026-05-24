/**
 * Saved-taxonomy list page.
 *
 * Lists every taxonomy saved on the backend and offers basic CRUD
 * (open / delete / new). The editor lives on
 * :mod:`./TaxonomyEditorPage`.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";

import {
  createTaxonomy,
  deleteTaxonomy,
  listTaxonomies,
} from "@/api/taxonomies";
import { Button } from "@/components/ui/button";
import type { TaxonomyListItem } from "@/schemas/taxonomy";

const TAXONOMY_LIST_QUERY_KEY = ["taxonomy-list"] as const;

export default function TaxonomyListPage(): JSX.Element {
  const navigate = useNavigate();
  const query_client = useQueryClient();

  const list_query = useQuery({
    queryKey: TAXONOMY_LIST_QUERY_KEY,
    queryFn: listTaxonomies,
    staleTime: 30_000,
  });

  const create_mutation = useMutation({
    mutationFn: () => createTaxonomy("Unnamed Codebook", {}),
    onSuccess: (response) => {
      query_client.invalidateQueries({ queryKey: TAXONOMY_LIST_QUERY_KEY });
      navigate(`/codebook/${encodeURIComponent(response.id)}`);
    },
  });

  const delete_mutation = useMutation({
    mutationFn: (taxonomy_id: string) => deleteTaxonomy(taxonomy_id),
    onSuccess: () => {
      query_client.invalidateQueries({ queryKey: TAXONOMY_LIST_QUERY_KEY });
    },
  });

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <h1 className="text-lg font-semibold">Codebook</h1>
        <Button
          disabled={create_mutation.isPending}
          onClick={() => create_mutation.mutate()}
        >
          <Plus className="mr-1 h-4 w-4" /> Create
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {list_query.isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : list_query.isError ? (
          <div className="text-sm text-destructive">
            Could not load taxonomies: {String(list_query.error)}
          </div>
        ) : (list_query.data ?? []).length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No codebooks saved yet.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Name</th>
                <th className="py-2 pr-3 font-medium">Updated</th>
                <th className="py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(list_query.data ?? []).map(
                (taxonomy_item: TaxonomyListItem) => (
                  <tr key={taxonomy_item.id} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-medium">
                      {taxonomy_item.name}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {new Date(taxonomy_item.updated_at).toLocaleString()}
                    </td>
                    <td className="py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            navigate(
                              `/codebook/${encodeURIComponent(
                                taxonomy_item.id,
                              )}`,
                            )
                          }
                        >
                          Open
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Delete codebook "${taxonomy_item.name}"? This cannot be undone.`,
                              )
                            ) {
                              delete_mutation.mutate(taxonomy_item.id);
                            }
                          }}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
