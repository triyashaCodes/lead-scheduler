function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const config = {
  apiBaseUrl: required(
    "NEXT_PUBLIC_API_BASE_URL",
    process.env.NEXT_PUBLIC_API_BASE_URL,
  ),
  googleClientId: required(
    "NEXT_PUBLIC_GOOGLE_CLIENT_ID",
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID,
  ),
  // Mirrors the backend RESUME_MAX_BYTES. Only used for early feedback; the
  // backend is the authority and rejects oversize files itself.
  resumeMaxBytes: Number(
    required(
      "NEXT_PUBLIC_RESUME_MAX_BYTES",
      process.env.NEXT_PUBLIC_RESUME_MAX_BYTES,
    ),
  ),
};
