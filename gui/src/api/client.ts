/**
 * Typed HTTP client for the agent_paper backend.
 *
 * Every API call in @/api/**.ts goes through :func:`requestJson`, which:
 *
 * 1. Prepends :data:`API_BASE_URL` to the caller-supplied path.
 * 2. Serialises an optional JSON body.
 * 3. Parses the response body through the caller-supplied Zod schema
 *    so the caller gets a strongly-typed result.
 * 4. Throws :class:`ApiError` on non-2xx responses, preserving the
 *    status code and the parsed :class:`ErrorResponse` body when the
 *    backend supplied one.
 *
 * This file is the only place fetch() lives; every feature module
 * imports :func:`requestJson`, :func:`requestBlob`, or
 * :func:`buildApiUrl` instead of composing URLs by hand.
 */

import type { ZodType, ZodTypeDef } from "zod";

import { errorResponseSchema, type ErrorResponse } from "@/schemas/errors";

/**
 * Base URL of the backend.
 *
 * Empty string in development (the Vite dev server proxies /api/**),
 * fully-qualified URL in production when the GUI is hosted on a
 * different origin than the backend.
 */
export const API_BASE_URL: string = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ""
).replace(/\/$/, "");

/**
 * Construct a full backend URL from a path like ``/api/flow/list``.
 *
 * @param path - Path starting with ``/``.
 * @returns Fully-qualified URL safe to pass to fetch or EventSource.
 */
export function buildApiUrl(path: string): string {
  if (!path.startsWith("/")) {
    throw new Error(
      `API path must start with '/': got ${JSON.stringify(path)}`,
    );
  }
  return `${API_BASE_URL}${path}`;
}

/**
 * Error raised by :func:`requestJson` for non-2xx responses.
 *
 * The ``errors`` field carries the parsed server error envelope
 * when the backend returned one; it is ``null`` otherwise (for
 * example when a proxy raised a 502 without a JSON body).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  readonly errors: ErrorResponse | null;

  constructor(
    message: string,
    status: number,
    url: string,
    errors: ErrorResponse | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.url = url;
    this.errors = errors;
  }
}

interface RequestJsonOptions<TResponse> {
  /** HTTP method, uppercase. */
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  /** Path starting with ``/``. */
  path: string;
  /** Zod schema the response body is parsed through. */
  responseSchema: ZodType<TResponse, ZodTypeDef, unknown>;
  /** Optional JSON body, serialised with ``JSON.stringify``. */
  jsonBody?: unknown;
  /** Extra request headers. */
  headers?: Record<string, string>;
  /** Optional AbortSignal for cancellation. */
  signal?: AbortSignal;
}

/**
 * Send an HTTP request, validate the response body, and return the
 * parsed result.
 *
 * @typeParam TResponse - Inferred from the ``responseSchema``.
 * @throws :class:`ApiError` on non-2xx status codes.
 */
export async function requestJson<TResponse>(
  options: RequestJsonOptions<TResponse>,
): Promise<TResponse> {
  const url = buildApiUrl(options.path);
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers ?? {}),
  };
  let body: BodyInit | undefined;
  if (options.jsonBody !== undefined) {
    body = JSON.stringify(options.jsonBody);
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    method: options.method,
    headers,
    body,
    signal: options.signal,
  });

  if (response.status === 204) {
    return options.responseSchema.parse(undefined);
  }

  const textBody = await response.text();
  if (!response.ok) {
    let parsedErrors: ErrorResponse | null = null;
    if (textBody) {
      try {
        parsedErrors = errorResponseSchema.parse(JSON.parse(textBody));
      } catch {
        parsedErrors = null;
      }
    }
    throw new ApiError(
      `${options.method} ${url} failed: HTTP ${response.status}`,
      response.status,
      url,
      parsedErrors,
    );
  }

  const jsonBody = textBody ? JSON.parse(textBody) : null;
  return options.responseSchema.parse(jsonBody);
}

/**
 * Fetch a URL and return the response body as a :class:`Blob`.
 *
 * Used by the artifact-download helpers so the browser can stream
 * large CSVs straight into ``URL.createObjectURL`` without going
 * through JSON parsing.
 *
 * @throws :class:`ApiError` on non-2xx status codes.
 */
export async function requestBlob(path: string): Promise<Blob> {
  const url = buildApiUrl(path);
  const response = await fetch(url, { method: "GET" });
  if (!response.ok) {
    throw new ApiError(
      `GET ${url} failed: HTTP ${response.status}`,
      response.status,
      url,
      null,
    );
  }
  return response.blob();
}
