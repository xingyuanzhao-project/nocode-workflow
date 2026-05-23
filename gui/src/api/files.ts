/**
 * API client for ``POST /api/files/upload``.
 *
 * Accepts CSV, JSON, and JSONL data files. Uploads are
 * multipart/form-data, not JSON; fetch builds the boundary
 * automatically when the body is a :class:`FormData`.
 */

import { ApiError, buildApiUrl, requestJson } from "./client";
import { errorResponseSchema } from "@/schemas/errors";
import {
  columnHeadersResponseSchema,
  csvUploadResponseSchema,
  dataFileListResponseSchema,
  type ColumnHeadersResponse,
  type CSVUploadResponse,
  type DataFileListResponse,
} from "@/schemas/files";

/**
 * List all uploaded and preloaded data files from the backend.
 */
export function listDataFiles(): Promise<DataFileListResponse> {
  return requestJson({
    method: "GET",
    path: "/api/files/list",
    responseSchema: dataFileListResponseSchema,
  });
}

/**
 * Fetch column headers for a stored CSV file.
 *
 * @param storedPath - The `stored_path` of the file as returned by the
 *   list or upload endpoint.
 * @returns Array of column header strings.
 */
export function fetchColumnHeaders(
  storedPath: string,
): Promise<ColumnHeadersResponse> {
  return requestJson({
    method: "GET",
    path: `/api/files/columns?path=${encodeURIComponent(storedPath)}`,
    responseSchema: columnHeadersResponseSchema,
  });
}

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
