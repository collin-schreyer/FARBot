import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, sessionToken } from "@/lib/auth";

// Cookie-based gate: unauthenticated users get redirected to a real /login page
// (no browser Basic Auth popup). The login form sets the session cookie.
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Always allow the login page + its API.
  if (pathname.startsWith("/login") || pathname.startsWith("/api/login") || pathname.startsWith("/api/logout")) {
    return NextResponse.next();
  }

  const authed = req.cookies.get(SESSION_COOKIE)?.value === sessionToken();
  if (authed) return NextResponse.next();

  if (pathname.startsWith("/api")) {
    return new NextResponse(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  }

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
