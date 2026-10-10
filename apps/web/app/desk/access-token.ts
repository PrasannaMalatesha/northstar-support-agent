import { getToken } from "next-auth/jwt";
import { cookies } from "next/headers";

// The API access token from the staff session cookie. Server code only.
export async function accessToken(): Promise<string | null> {
  const cookieHeader = (await cookies()).toString();
  const token = await getToken({
    req: new Request("http://localhost", { headers: { cookie: cookieHeader } }),
    secret: process.env.AUTH_SECRET,
  });
  return typeof token?.accessToken === "string" ? token.accessToken : null;
}
