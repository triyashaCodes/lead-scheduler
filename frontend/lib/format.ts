export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    // Non-breaking space keeps the number and unit on one line.
    return `${Math.round((bytes / (1024 * 1024)) * 10) / 10}\u00A0MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))}\u00A0KB`;
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}
