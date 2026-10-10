import { auth } from "@/auth";
import { NextResponse } from "next/server";

export default auth((request) => {
  const signedIn = Boolean(request.auth);
  const onLogin = request.nextUrl.pathname === "/login";
  // Redirects keep the host the browser used (specialist.localhost, 127.0.0.1, or the real domain).
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? request.nextUrl.host;
  const here = `${request.nextUrl.protocol}//${host}`;
  if (!signedIn && !onLogin) {
    return NextResponse.redirect(new URL("/login", here));
  }
  // "expired": the API refused the session's token. The sign-in page shows instead of bouncing to the desk.
  if (signedIn && onLogin && !request.nextUrl.searchParams.has("expired")) {
    return NextResponse.redirect(new URL("/desk", here));
  }

  // Some browsers send the literal origin "null" (sandboxed or privacy mode).
  // Next.js throws before the action runs. Keep cross-site posts blocked.
  if (request.headers.get("origin") === "null") {
    if (request.headers.get("sec-fetch-site") === "cross-site") {
      return new NextResponse("Cross-site request blocked.", { status: 403 });
    }
    const headers = new Headers(request.headers);
    const host =
      request.headers.get("x-forwarded-host") ??
      request.headers.get("host") ??
      request.nextUrl.host;
    headers.set("origin", `${request.nextUrl.protocol}//${host}`);
    return NextResponse.next({ request: { headers } });
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/desk/:path*", "/login"],
  // Node.js, not the edge: the session renewal in staff-session.ts is shared with the page in the same process.
  runtime: "nodejs",
};
