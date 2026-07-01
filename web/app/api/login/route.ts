import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, sessionToken, validCredentials } from "@/lib/auth";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const { username, password } = (await req.json().catch(() => ({}))) as {
    username?: string;
    password?: string;
  };
  if (!validCredentials(username ?? "", password ?? "")) {
    return NextResponse.json({ error: "Invalid username or password." }, { status: 401 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, sessionToken(), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return res;
}
