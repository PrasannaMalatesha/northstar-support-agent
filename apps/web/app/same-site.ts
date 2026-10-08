import { headers } from "next/headers";

export const apiUrl = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";

// A server action runs only for a same-site form post.
export async function sameSite(): Promise<boolean> {
  const headerList = await headers();
  const host = headerList.get("host");
  const origin = headerList.get("origin");
  const site = headerList.get("sec-fetch-site");
  if (!host || site === "cross-site") {
    return false;
  }
  if (!origin || origin === "null") {
    return site === "same-origin" || site === "none";
  }
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
