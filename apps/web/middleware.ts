import { auth } from "@/auth";
import { NextResponse } from "next/server";

export default auth((request) => {
  const signedIn = Boolean(request.auth);
  const onLogin = request.nextUrl.pathname === "/login";
  if (!signedIn && !onLogin) {
    return NextResponse.redirect(new URL("/login", request.nextUrl));
  }
  if (signedIn && onLogin) {
    return NextResponse.redirect(new URL("/desk", request.nextUrl));
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
};
