import { clearToken, getToken } from "@/lib/auth";
import { config } from "@/lib/config";
import type { Lead, LeadCreated, LeadList, LeadState } from "@/lib/types";
import {
  FIELD_MESSAGES,
  RESUME_EMPTY_MESSAGE,
  RESUME_TYPE_MESSAGE,
  resumeTooLargeMessage,
  type FieldErrors,
  type FieldName,
} from "@/lib/validation";

export interface LeadSubmission {
  firstName: string;
  lastName: string;
  email: string;
  resume: File;
  // Honeypot: hidden from people, so it should always be empty.
  website: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fieldErrors: FieldErrors = {},
  ) {
    super(message);
  }
}

const NETWORK_MESSAGE =
  "We couldn't reach the server. Check your connection and try again.";
const SERVER_MESSAGE = "Something went wrong on our side. Try again in a moment.";
const FIELDS_MESSAGE = "Check the highlighted fields and try again.";

function isFieldName(value: unknown): value is FieldName {
  return typeof value === "string" && value in FIELD_MESSAGES;
}

function fieldErrorsFromDetail(detail: unknown): FieldErrors {
  const errors: FieldErrors = {};
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : null;
      if (isFieldName(field)) errors[field] = FIELD_MESSAGES[field];
    }
  }
  return errors;
}

export async function submitLead(submission: LeadSubmission): Promise<LeadCreated> {
  const body = new FormData();
  body.append("first_name", submission.firstName.trim());
  body.append("last_name", submission.lastName.trim());
  body.append("email", submission.email.trim());
  body.append("website", submission.website);
  body.append("resume", submission.resume);

  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}/leads`, { method: "POST", body });
  } catch {
    throw new ApiError(NETWORK_MESSAGE, 0);
  }

  if (response.ok) {
    return (await response.json()) as LeadCreated;
  }

  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;

  if (response.status === 429) {
    throw new ApiError(
      "Too many submissions from your connection. Wait a little while and try again.",
      429,
    );
  }
  if (response.status === 413) {
    throw new ApiError(FIELDS_MESSAGE, 413, {
      resume: resumeTooLargeMessage(config.resumeMaxBytes),
    });
  }
  if (response.status === 415) {
    throw new ApiError(FIELDS_MESSAGE, 415, { resume: RESUME_TYPE_MESSAGE });
  }
  if (response.status === 422) {
    // A string detail is the backend's "empty resume" error; an array is
    // field validation.
    const fieldErrors =
      typeof detail === "string"
        ? { resume: RESUME_EMPTY_MESSAGE }
        : fieldErrorsFromDetail(detail);
    throw new ApiError(FIELDS_MESSAGE, 422, fieldErrors);
  }
  throw new ApiError(SERVER_MESSAGE, response.status);
}

// Attorney endpoints. The token is read from storage and sent as a Bearer
// header; a 401 clears it, which returns the attorney to sign-in.

const SESSION_ENDED_MESSAGE = "Your session ended. Sign in again.";
const NOT_ATTORNEY_MESSAGE =
  "This Google account is not on the attorney list. Sign out and use a different account.";

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  if (!token) {
    clearToken(SESSION_ENDED_MESSAGE);
    throw new ApiError(SESSION_ENDED_MESSAGE, 401);
  }

  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError(NETWORK_MESSAGE, 0);
  }

  if (response.status === 401) {
    clearToken(SESSION_ENDED_MESSAGE);
    throw new ApiError(SESSION_ENDED_MESSAGE, 401);
  }
  if (response.status === 403) throw new ApiError(NOT_ATTORNEY_MESSAGE, 403);
  return response;
}

function failure(response: Response, notFound: string): ApiError {
  if (response.status === 404) return new ApiError(notFound, 404);
  return new ApiError(SERVER_MESSAGE, response.status);
}

export async function listLeads(options: {
  state?: LeadState | null;
  page?: number;
  pageSize?: number;
}): Promise<LeadList> {
  const query = new URLSearchParams();
  if (options.state) query.set("state", options.state);
  if (options.page) query.set("page", String(options.page));
  if (options.pageSize) query.set("page_size", String(options.pageSize));

  const response = await authedFetch(`/leads?${query}`);
  if (!response.ok) throw failure(response, "Those leads could not be found.");
  return (await response.json()) as LeadList;
}

export async function getLead(id: string): Promise<Lead> {
  const response = await authedFetch(`/leads/${encodeURIComponent(id)}`);
  if (!response.ok) throw failure(response, "That lead does not exist.");
  return (await response.json()) as Lead;
}

export async function markReachedOut(id: string): Promise<Lead> {
  const response = await authedFetch(`/leads/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state: "REACHED_OUT" }),
  });
  if (response.status === 409) {
    throw new ApiError("Another attorney already marked this lead as reached out.", 409);
  }
  if (!response.ok) throw failure(response, "That lead does not exist.");
  return (await response.json()) as Lead;
}

function filenameFromDisposition(header: string | null): string {
  if (header) {
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (encoded) {
      try {
        return decodeURIComponent(encoded[1]);
      } catch {
        // Fall through to the plain form.
      }
    }
    const plain = /filename="([^"]+)"/i.exec(header);
    if (plain) return plain[1];
  }
  return "resume";
}

export async function downloadResume(
  id: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await authedFetch(`/leads/${encodeURIComponent(id)}/resume`);
  if (!response.ok) throw failure(response, "The resume file could not be found.");
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition")),
  };
}
