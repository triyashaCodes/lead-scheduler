// Holds the Google ID token in sessionStorage: it survives a reload but not a
// closed tab. The backend verifies the token; nothing here is trusted.
const TOKEN_KEY = "attorney-id-token";

const listeners = new Set<() => void>();
let notice: string | null = null;

function notify() {
  listeners.forEach((listener) => listener());
}

function payloadOf(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  try {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) return null;
    const exp = payloadOf(token)?.exp;
    if (typeof exp === "number" && exp * 1000 <= Date.now()) return null;
    return token;
  } catch {
    return null;
  }
}

// For display only, so the header can show who is signed in.
export function emailFromToken(token: string): string | null {
  const email = payloadOf(token)?.email;
  return typeof email === "string" ? email : null;
}

export function setToken(token: string) {
  notice = null;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage can be blocked; the user just has to sign in again next time.
  }
  notify();
}

export function clearToken(reason: string | null = null) {
  notice = reason;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing to clear.
  }
  notify();
}

export function getNotice(): string | null {
  return notice;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
