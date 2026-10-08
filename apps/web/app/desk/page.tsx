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

async function closeAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  const status = String(formData.get("status") ?? "");
  const path = status === "Escalated" ? "escalate" : "resolve";
  await fetch(`${apiUrl}/cases/current/${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${access}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ final_text: String(formData.get("final_text") ?? "") }),
  });
  redirect("/desk");
}

async function editAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  await fetch(`${apiUrl}/approvals/${String(formData.get("case_id") ?? "")}/edit`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${access}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ amount_cents: Number(formData.get("amount_cents")) }),
  });
  redirect("/desk");
}

async function rejectAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  await fetch(`${apiUrl}/approvals/${String(formData.get("case_id") ?? "")}/reject`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${access}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ reason: String(formData.get("reason") ?? "") }),
  });
  redirect("/desk");
}

async function approveAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  const approved = await fetch(`${apiUrl}/approvals/${String(formData.get("case_id") ?? "")}/approve`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access}` },
  });
  const body = (await approved.json()) as { ticket_id?: string };
  redirect(body.ticket_id ? `/desk?ticket=${body.ticket_id}` : "/desk");
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

async function newCaseAction() {
  "use server";
  if (!(await sameSite())) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  await fetch(`${apiUrl}/cases/current/new`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access}` },
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

export default async function DeskPage({
  searchParams,
}: {
  searchParams: Promise<{ ticket?: string; case?: string }>;
}) {
  const params = await searchParams;
  const ticket = params.ticket;
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  // A lead opens a queue row as a read-only case desk.
  const viewing = session.user.role === "lead" && typeof params.case === "string" && /^[0-9a-f-]{36}$/.test(params.case);
  const response = await fetch(viewing ? `${apiUrl}/cases/${params.case}` : `${apiUrl}/cases/current`, {
    headers: { Authorization: `Bearer ${access}` },
    cache: "no-store",
  });
  if (!response.ok) {
    redirect("/login");
  }
  const waiting =
    session.user.role === "lead"
      ? await fetch(`${apiUrl}/approvals`, {
          headers: { Authorization: `Bearer ${access}` },
          cache: "no-store",
        }).then(async (waitingResponse) =>
          waitingResponse.ok
            ? ((await waitingResponse.json()) as {
                case_id: string;
                action: string;
                amount_cents: number | null;
                order_id: string;
                details: string;
                citations: string[];
                order_summary: string;
                age_seconds: number;
                stale: boolean;
                question: string;
                draft: string;
              }[])
            : [],
        )
      : [];

  const current = (await response.json()) as {
    status: string;
    stale: boolean;
    draft_text: string;
    final_text: string;
    customer: { name: string; email: string } | null;
    history: {
      id: string;
      status: string;
      outcome: string;
      refunded_lines: string[];
    }[];
    ticket_id: string | null;
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
      {ticket ? <p>Ticket {ticket}.</p> : null}
      {current.ticket_id ? <p>Ticket {current.ticket_id}.</p> : null}
      {session.user.role === "lead" ? (
        <section>
          <h2>Waiting for approval</h2>
          {waiting.length === 0 ? <p>No proposal is waiting.</p> : null}
          {waiting.map((item) => (
            <article key={item.case_id}>
              <p>
                {item.order_id}: {item.action}
                {item.amount_cents !== null ? `, ${item.amount_cents} cents` : ""}
                {item.details ? `, ${item.details}` : ""}, {item.age_seconds} seconds
                {item.stale ? " Stale." : ""}
              </p>
              <p>{item.question}</p>
              <p>{item.draft}</p>
              {item.order_summary ? <p className="quiet">Order: {item.order_summary}</p> : null}
              {item.citations.length > 0 ? <p className="quiet">Cited: {item.citations.join(", ")}</p> : null}
              <p>
                <a href={`/desk?case=${item.case_id}`}>Open case {item.order_id}</a>
              </p>
              <form action={approveAction}>
                <input type="hidden" name="case_id" value={item.case_id} />
                <button type="submit">Approve</button>
              </form>
              {item.amount_cents !== null ? (
                <form action={editAction}>
                  <input type="hidden" name="case_id" value={item.case_id} />
                  <label>
                    Amount in cents
                    <input name="amount_cents" type="number" min={0} required />
                  </label>
                  <button type="submit">Edit amount</button>
                </form>
              ) : null}
              <form action={rejectAction}>
                <input type="hidden" name="case_id" value={item.case_id} />
                <label>
                  Reason
                  <input name="reason" type="text" required />
                </label>
                <button type="submit">Reject</button>
              </form>
            </article>
          ))}
        </section>
      ) : null}
      {viewing ? (
        <p>
          Reading case {params.case}. <a href="/desk">Back to my desk</a>
        </p>
      ) : null}
      <p className="quiet">
        {current.status}
        {current.stale ? " Stale." : ""}
      </p>
      <p>{current.customer ? current.customer.name : "No customer bound."}</p>
      <section>
        <h2>Past cases</h2>
        {current.history.length === 0 ? (
          <p>No past cases.</p>
        ) : (
          <ul>
            {current.history.map((item) => (
              <li key={item.id}>
                {item.id}. {item.status}. {item.outcome}.
                {item.refunded_lines.length > 0
                  ? ` Refunded: ${item.refunded_lines.join(", ")}.`
                  : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
      {!viewing && (current.status === "Resolved" || current.status === "Escalated") ? (
        <form action={newCaseAction}>
          <button type="submit">New case</button>
        </form>
      ) : null}
      {current.draft_text ? (
        <article className="turn">
          <p className="quiet">Agent draft</p>
          <p>{current.draft_text}</p>
        </article>
      ) : null}
      {current.final_text ? (
        <article className="turn">
          <p className="quiet">Final text</p>
          <p>{current.final_text}</p>
        </article>
      ) : null}
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
      {!viewing && current.status === "Open" ? (
        <>
          <form action={bindAction}>
            <label>
              Customer email or phone
              <input name="query" type="text" autoComplete="off" required />
            </label>
            <button type="submit">Bind</button>
          </form>
          <form action={askAction}>
            <label>
              Handbook question
              <textarea name="question" required maxLength={2000} />
            </label>
            <button type="submit">Ask</button>
          </form>
          <form action={closeAction}>
            <label>
              Final text
              <textarea name="final_text" required maxLength={4000} />
            </label>
            <button type="submit" name="status" value="Resolved">
              Resolve
            </button>
            <button type="submit" name="status" value="Escalated">
              Escalate
            </button>
          </form>
        </>
      ) : null}
      <form action={logoutAction}>
        <button type="submit">Log out</button>
      </form>
    </main>
  );
}
