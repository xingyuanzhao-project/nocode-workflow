/**
 * API client for ``POST /api/files/upload``.
 *
 * Accepts CSV, JSON, and JSONL data files. Uploads are
 * multipart/form-data, not JSON; fetch builds the boundary
 * automatically when the body is a :class:`FormData`.
 */

import { ApiError, buildApiUrl } from "./client";
import { errorResponseSchema } from "@/schemas/errors";
import {
  csvUploadResponseSchema,
  type CSVUploadResponse,
} from "@/schemas/files";

/**
 * Upload a data file (CSV, JSON, or JSONL) and receive its inspection summary.
 *
 * @param file - File handle from an ``<input type="file" />`` or a
 *   drag-and-drop event.
 * @returns Parsed :class:`CSVUploadResponse` including the
 *   ``stored_path`` the GUI uses as the flow's ``input_csv``.
 * @throws :class:`ApiError` on non-2xx responses.
 */
export async function uploadCsv(file: File): Promise<CSVUploadResponse> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  const url = buildApiUrl("/api/files/upload");
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });
  const rawBody = await response.text();
  if (!response.ok) {
    let parsedErrors = null;
    if (rawBody) {
      try {
        parsedErrors = errorResponseSchema.parse(JSON.parse(rawBody));
      } catch {
        parsedErrors = null;
      }
    }
    throw new ApiError(
      `POST ${url} failed: HTTP ${response.status}`,
      response.status,
      url,
      parsedErrors,
    );
  }
  return csvUploadResponseSchema.parse(rawBody ? JSON.parse(rawBody) : null);
}
