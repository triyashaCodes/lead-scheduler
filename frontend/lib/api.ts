import { config } from "@/lib/config";
import {
  FIELD_MESSAGES,
  RESUME_EMPTY_MESSAGE,
  RESUME_TYPE_MESSAGE,
  resumeTooLargeMessage,
  type FieldErrors,
  type FieldName,
} from "@/lib/validation";

// Mirrors backend schemas/lead.py LeadCreated.
export interface LeadCreated {
  id: string;
}

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
