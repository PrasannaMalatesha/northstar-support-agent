import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { apiUrl, sameSite } from "../same-site";

// Customer chat (issue #79). The customer gives an order id and the email on that order.
// The chat token lives in an httpOnly cookie, so browser code never reads it.
const COOKIE = "northstar_chat";

type ChatView = { status: string; messages: { role: string; text: string }[] };

async function chatToken(): Promise<string | null> {
  return (await cookies()).get(COOKIE)?.value ?? null;
}

async function startAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/chat");
  }
  const started = await fetch(`${apiUrl}/chat/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      order_id: String(formData.get("order_id") ?? ""),
      email: String(formData.get("email") ?? ""),
    }),
  });
  if (!started.ok) {
    redirect(started.status === 423 ? "/chat?error=locked" : "/chat?error=nomatch");
  }
  const body = (await started.json()) as { chat_token: string };
  (await cookies()).set(COOKIE, body.chat_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/chat",
    maxAge: 30 * 60,
  });
  redirect("/chat");
}

async function sendAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/chat");
  }
  const token = await chatToken();
  if (!token) {
    redirect("/chat");
  }
  const sent = await fetch(`${apiUrl}/chat/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ question: String(formData.get("question") ?? "") }),
  });
  if (!sent.ok) {
    redirect(sent.status === 409 ? "/chat?error=waiting" : "/chat?error=unsent");
  }
  redirect("/chat");
}

async function endAction() {
  "use server";
  if (!(await sameSite())) {
    redirect("/chat");
  }
  (await cookies()).delete({ name: COOKIE, path: "/chat" });
  redirect("/chat");
}

const ERRORS: Record<string, string> = {
  nomatch: "That order and email do not match.",
  locked: "Too many tries. Try again later.",
  waiting: "Your request is with our team. You can write again once they reply.",
  unsent: "That message was not sent. Try again.",
};

export default async function ChatPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  const token = await chatToken();
  const shown = token
    ? await fetch(`${apiUrl}/chat`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" })
    : null;
  const view = shown?.ok ? ((await shown.json()) as ChatView) : null;

  if (!view) {
    return (
      <main>
        <h1>Northstar support chat</h1>
        <p>Enter an order id and the email used for that order.</p>
        {error && ERRORS[error] ? <p role="alert">{ERRORS[error]}</p> : null}
        <form action={startAction}>
          <label>
            Order id
            <input name="order_id" type="text" autoComplete="off" required maxLength={20} />
          </label>
          <label>
            Email
            <input name="email" type="email" autoComplete="email" required maxLength={320} />
          </label>
          <button type="submit">Start chat</button>
        </form>
      </main>
    );
  }

  return (
    <main>
      <h1>Northstar support chat</h1>
      {view.status ? <p role="status">{view.status}</p> : null}
      {error && ERRORS[error] ? <p role="alert">{ERRORS[error]}</p> : null}
      <section aria-label="Conversation">
        {view.messages.length === 0 ? <p>Ask about returns, shipping, warranty, or your orders.</p> : null}
        <ol>
          {view.messages.map((message, index) => (
            <li key={index}>
              <strong>{message.role === "user" ? "You" : "Northstar"}:</strong> {message.text}
            </li>
          ))}
        </ol>
      </section>
      <form action={sendAction}>
        <label>
          Your message
          <textarea name="question" required maxLength={2000} />
        </label>
        <button type="submit">Send</button>
      </form>
      <form action={endAction}>
        <button type="submit">End chat</button>
      </form>
    </main>
  );
}
