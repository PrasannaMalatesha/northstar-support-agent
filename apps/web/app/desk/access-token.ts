import { getToken } from "next-auth/jwt";
import { cookies } from "next/headers";
import { endsSoon, renew } from "@/staff-session";

// The API access token from the staff session cookie. Server code only.
// When it is about to end, this request uses the renewal the middleware made for the same cookie.
export async function accessToken(): Promise<string | null> {
  const cookieHeader = (await cookies()).toString();
  const token = await getToken({
    req: new Request("http://localhost", { headers: { cookie: cookieHeader } }),
    secret: process.env.AUTH_SECRET,
  });
  if (typeof token?.accessToken !== "string") {
    return null;
  }
  if (!endsSoon(token.accessToken)) {
    return token.accessToken;
  }
  const renewed = typeof token.refreshToken === "string" ? await renew(token.refreshToken) : null;
  return renewed?.accessToken ?? null;
}
