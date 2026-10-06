import { auth, signOut } from "@/auth";
import { getToken } from "next-auth/jwt";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

const apiUrl = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";

async function accessToken(): Promise<string | null> {
  const cookieHeader = (await cookies()).toString();
  const token = await getToken({
    req: new Request("http://localhost", { headers: { cookie: cookieHeader } }),
    secret: process.env.AUTH_SECRET,
  });
  return typeof token?.accessToken === "string" ? token.accessToken : null;
}

async function sameSite(): Promise<boolean> {
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

async function bindAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  await fetch(`${apiUrl}/cases/current/customer`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${access}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query: String(formData.get("query") ?? "") }),
  });
  redirect("/desk");
}

async function askAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  await fetch(`${apiUrl}/cases/current/messages`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${access}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question: String(formData.get("question") ?? "") }),
  });
  redirect("/desk");
}

async function logoutAction() {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const token = await getToken({
    req: new Request("http://localhost", {
      headers: { cookie: (await cookies()).toString() },
    }),
    secret: process.env.AUTH_SECRET,
  });
  const refreshToken = token?.refreshToken;
  if (typeof refreshToken === "string") {
    await fetch(`${apiUrl}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }
  await signOut({ redirectTo: "/login" });
}

export default async function DeskPage() {
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  const response = await fetch(`${apiUrl}/cases/current`, {
    headers: { Authorization: `Bearer ${access}` },
    cache: "no-store",
  });
  if (!response.ok) {
    redirect("/login");
  }
  const current = (await response.json()) as {
    customer: { name: string; email: string } | null;
    messages: {
      role: string;
      body: string;
      decision: string | null;
      citations: string[];
      match: Record<string, string>;
      steps: string[];
    }[];
  };

  return (
    <main className="desk">
      <p className="quiet">
        {session.user.name} · {session.user.role}
      </p>
      <h1>Case desk</h1>
      <p>{current.customer ? current.customer.name : "No customer bound."}</p>
      <form action={bindAction}>
        <label>
          Customer email or phone
          <input name="query" type="text" autoComplete="off" required />
        </label>
        <button type="submit">Bind</button>
      </form>
      {current.messages.length === 0 ? (
        <p>Ask a handbook question.</p>
      ) : (
        current.messages.map((message, index) => (
          <article className="turn" key={`${message.role}-${index}`}>
            <p className="quiet">{message.role === "user" ? "Question" : "Draft"}</p>
            {message.steps.length > 0 ? (
              <ol>
                {message.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            ) : null}
            <p>{message.body}</p>
            {message.citations.length > 0 ? (
              <p className="quiet">
                Cited:{" "}
                {message.citations
                  .map((sectionId) =>
                    message.match[sectionId]
                      ? `${sectionId} (${message.match[sectionId]})`
                      : sectionId,
                  )
                  .join(", ")}
              </p>
            ) : null}
          </article>
        ))
      )}
      <form action={askAction}>
        <label>
          Handbook question
          <textarea name="question" required maxLength={2000} />
        </label>
        <button type="submit">Ask</button>
      </form>
      <form action={logoutAction}>
        <button type="submit">Log out</button>
      </form>
    </main>
  );
}
