/**
 * Pre-run confirmation dialog showing a rough cost estimate.
 *
 * Shown after the user clicks "Run" but before the flow is actually
 * submitted. The dialog fetches an estimate from
 * ``POST /api/flow/estimate-cost`` and asks the user to confirm.
 *
 * The estimate is intentionally rough (chars / 4 ~ tokens, times a
 * per-model rate). Its purpose is to catch accidental large runs, not
 * to produce an exact bill.
 */

import { useEffect } from "react";
import { useMutation } from "@tanstack/react-query";

import { estimateCost } from "@/api/flows";
import type { CostEstimateResponse } from "@/schemas/flow";
import { Button } from "@/components/ui/button";

export interface CostEstimateDialogProps {
  /** The flow body that would be submitted. */
  flow_body: Record<string, unknown>;
  /** Called when the user confirms the run. */
  on_confirm: () => void;
  /** Called when the user cancels. */
  on_cancel: () => void;
}

export function CostEstimateDialog({
  flow_body,
  on_confirm,
  on_cancel,
}: CostEstimateDialogProps): JSX.Element {
  const estimate_mutation = useMutation({
    mutationFn: () => {
      const data_block = flow_body.data as
        | Record<string, unknown>
        | undefined;
      const input_csv = data_block?.input_csv;
      const row_count_guess = typeof input_csv === "string" ? 100 : 100;
      const char_count_guess = row_count_guess * 2000;
      return estimateCost(flow_body, row_count_guess, char_count_guess);
    },
  });

  useEffect(() => {
    estimate_mutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const estimate: CostEstimateResponse | undefined =
    estimate_mutation.data ?? undefined;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg">
        <h2 className="text-base font-semibold">Confirm Run</h2>

        {estimate_mutation.isPending ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Estimating cost...
          </p>
        ) : estimate_mutation.error ? (
          <p className="mt-3 text-sm text-destructive">
            Could not estimate cost. You can still proceed.
          </p>
        ) : estimate ? (
          <div className="mt-3 space-y-2">
            <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Model</span>
                <span className="font-mono text-xs">{estimate.model}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Steps</span>
                <span>{estimate.step_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Est. tokens</span>
                <span>{estimate.estimated_tokens.toLocaleString()}</span>
              </div>
              <div className="mt-1 flex justify-between border-t pt-1 font-medium">
                <span>Est. cost</span>
                <span>
                  ${estimate.estimated_cost_usd < 0.01
                    ? "< 0.01"
                    : estimate.estimated_cost_usd.toFixed(2)}
                </span>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              This is a rough order-of-magnitude estimate. Actual cost
              depends on the provider&apos;s billing and the data size.
            </p>
          </div>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={on_cancel}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={on_confirm}
            disabled={estimate_mutation.isPending}
          >
            {estimate_mutation.isPending ? "Estimating..." : "Run"}
          </Button>
        </div>
      </div>
    </div>
  );
}
