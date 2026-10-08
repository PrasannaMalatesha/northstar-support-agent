"use server";

import { signIn } from "@/auth";
import { AuthError } from "next-auth";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

const apiUrl = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";

async function sameOrigin(): Promise<boolean> {
  const headerList = await headers();
  const host = headerList.get("host");
  const site = headerList.get("sec-fetch-site");
  if (!host) {
    return false;
  }
  if (site === "cross-site") {
    return false;
  }
  const origin = headerList.get("origin");
  if (!origin || origin === "null") {
    return site === "same-origin" || site === "none";
  }
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export async function loginAction(formData: FormData) {
  // With single sign-on on, the password path is closed (issue #78).
  if (process.env.AUTH_GOOGLE_ID || !(await sameOrigin())) {
    redirect("/login?error=1");
  }
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const checked = await fetch(`${apiUrl}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (checked.status === 423) {
    redirect("/login?error=locked");
  }
  if (!checked.ok) {
    redirect("/login?error=1");
  }
  try {
    await signIn("credentials", { email, password, redirectTo: "/desk" });
  } catch (error) {
    if (error instanceof AuthError) {
      redirect("/login?error=1");
    }
    throw error;
  }
}
