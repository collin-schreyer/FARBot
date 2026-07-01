export const SESSION_COOKIE = "far_auth";

export function adminUser(): string {
  return process.env.ADMIN_USER ?? "B&A";
}
export function adminPass(): string {
  return process.env.ADMIN_PASS ?? "F&A_chat2026";
}
// Opaque session value placed in the cookie after a successful login.
// Set SESSION_TOKEN in the environment for a real secret; the fallback keeps
// local dev working.
export function sessionToken(): string {
  return process.env.SESSION_TOKEN ?? "far-assistant-session-v1";
}
export function validCredentials(u: string, p: string): boolean {
  return u === adminUser() && p === adminPass();
}
