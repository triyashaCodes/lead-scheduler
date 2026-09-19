import { formatBytes } from "@/lib/format";

export type FieldName = "first_name" | "last_name" | "email" | "resume";
export type FieldErrors = Partial<Record<FieldName, string>>;

export const ALLOWED_EXTENSIONS = ["pdf", "doc", "docx"];

export const FIELD_MESSAGES: Record<FieldName, string> = {
  first_name: "Enter your first name.",
  last_name: "Enter your last name.",
  email: "Enter a valid email address.",
  resume: "Choose a resume file.",
};

export const RESUME_TYPE_MESSAGE = "Upload a PDF, DOC or DOCX file.";

export function resumeTooLargeMessage(maxBytes: number): string {
  return `That file is over ${formatBytes(maxBytes)}. Choose a smaller one.`;
}

export const RESUME_EMPTY_MESSAGE = "That file is empty. Choose a different one.";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface FormValues {
  firstName: string;
  lastName: string;
  email: string;
}

// Early feedback only. The backend re-checks everything, including the real
// file type (by content, not by name).
export function validate(
  values: FormValues,
  resume: File | null,
  maxBytes: number,
): FieldErrors {
  const errors: FieldErrors = {};
  if (!values.firstName.trim()) errors.first_name = FIELD_MESSAGES.first_name;
  if (!values.lastName.trim()) errors.last_name = FIELD_MESSAGES.last_name;
  if (!EMAIL_PATTERN.test(values.email.trim())) errors.email = FIELD_MESSAGES.email;

  if (!resume) {
    errors.resume = FIELD_MESSAGES.resume;
  } else {
    const extension = resume.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      errors.resume = RESUME_TYPE_MESSAGE;
    } else if (resume.size === 0) {
      errors.resume = RESUME_EMPTY_MESSAGE;
    } else if (resume.size > maxBytes) {
      errors.resume = resumeTooLargeMessage(maxBytes);
    }
  }
  return errors;
}
