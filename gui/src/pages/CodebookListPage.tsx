/**
 * Saved-codebook list page.
 *
 * Lists every codebook saved on the backend and offers basic CRUD
 * (open / delete / new). The editor lives on
 * :mod:`./CodebookEditorPage`.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";

import {
  createCodebook,
  deleteCodebook,
  listCodebooks,
} from "@/api/codebooks";
import { Button } from "@/components/ui/button";
import type { CodebookListItem } from "@/schemas/codebook";

const CODEBOOK_LIST_QUERY_KEY = ["codebook-list"] as const;

export default function CodebookListPage(): JSX.Element {
  const navigate = useNavigate();
  const query_client = useQueryClient();

  const list_query = useQuery({
    queryKey: CODEBOOK_LIST_QUERY_KEY,
    queryFn: listCodebooks,
    staleTime: 30_000,
  });

  const create_mutation = useMutation({
    mutationFn: () => createCodebook("Unnamed Codebook", {}),
    onSuccess: (response) => {
      query_client.invalidateQueries({ queryKey: CODEBOOK_LIST_QUERY_KEY });
      navigate(`/codebook/${encodeURIComponent(response.id)}`);
    },
  });

  const delete_mutation = useMutation({
    mutationFn: (codebook_id: string) => deleteCodebook(codebook_id),
    onSuccess: () => {
      query_client.invalidateQueries({ queryKey: CODEBOOK_LIST_QUERY_KEY });
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
            Could not load codebooks: {String(list_query.error)}
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
                (codebook_item: CodebookListItem) => (
                  <tr key={codebook_item.id} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-medium">
                      {codebook_item.name}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {new Date(codebook_item.updated_at).toLocaleString()}
                    </td>
                    <td className="py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            navigate(
                              `/codebook/${encodeURIComponent(
                                codebook_item.id,
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
                                `Delete codebook "${codebook_item.name}"? This cannot be undone.`,
                              )
                            ) {
                              delete_mutation.mutate(codebook_item.id);
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
