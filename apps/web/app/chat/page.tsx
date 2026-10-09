import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { Refresh } from "../refresh";
import { apiUrl, sameSite } from "../same-site";

// Customer chat (issue #79). The customer gives an order id and the email on that order.
// The chat token lives in an httpOnly cookie, so browser code never reads it.
const COOKIE = "northstar_chat";

type ChatView = { status: string; messages: { role: string; name?: string; text: string }[] };
// What the chat offers beside the agent (R35). "leave_message" after replies that did not help.
// `live` is the customer's open live chat request (issue #138), null when there is none.
// "idle" means the customer went quiet: writing again brings the person back (issue #142).
type ChatState = {
  offer: string | null;
  live_enabled: boolean;
  live: { status: "waiting" | "offered" | "active" | "idle"; specialist: string | null } | null;
};

function liveNote(live: NonNullable<ChatState["live"]>): string {
  if (live.status === "active") {
    return `${live.specialist} joined the chat.`;
  }
  return live.status === "idle" ? "Your chat with a person is paused. Write to carry on." : "Waiting for a person.";
}

function speaker(message: ChatView["messages"][number]): string {
  if (message.role === "user") {
    return "You";
  }
  return message.role === "specialist" ? `${message.name}, Northstar specialist` : "Northstar";
}

async function chatToken(): Promise<string | null> {
  return (await cookies()).get(COOKIE)?.value ?? null;
}

async function keepToken(token: string) {
  (await cookies()).set(COOKIE, token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/chat",
    maxAge: 30 * 60,
  });
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
  await keepToken(body.chat_token);
  redirect("/chat");
}

async function liveAction() {
  "use server";
  if (!(await sameSite())) {
    redirect("/chat");
  }
  const token = await chatToken();
  if (!token) {
    redirect("/chat");
  }
  const asked = await fetch(`${apiUrl}/chat/live`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!asked.ok) {
    redirect(asked.status === 409 ? "/chat?error=waiting" : "/chat?error=nolive");
  }
  redirect("/chat");
}

// The chat is not signed out while the customer waits for or talks to a specialist (R47).
async function renewAction() {
  "use server";
  const token = await chatToken();
  if (!(await sameSite()) || !token) {
    return;
  }
  const renewed = await fetch(`${apiUrl}/chat/renew`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (renewed.ok) {
    await keepToken(((await renewed.json()) as { chat_token: string }).chat_token);
  }
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

async function leaveAction(formData: FormData) {
  "use server";
  if (!(await sameSite())) {
    redirect("/chat");
  }
  const token = await chatToken();
  if (!token) {
    redirect("/chat");
  }
  const left = await fetch(`${apiUrl}/chat/leave-message`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ text: String(formData.get("message") ?? "") }),
  });
  if (!left.ok) {
    redirect(left.status === 409 ? "/chat?error=nooffer" : "/chat?error=unsent");
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
  nooffer: "Leaving a message is offered after replies that did not help.",
  nolive: "We could not ask for a person. Try again.",
};

export default async function ChatPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  const token = await chatToken();
  const shown = token
    ? await fetch(`${apiUrl}/chat`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" })
    : null;
  const view = shown?.ok ? ((await shown.json()) as ChatView) : null;
  const stated = view
    ? await fetch(`${apiUrl}/chat/state`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" })
    : null;
  const state = stated?.ok ? ((await stated.json()) as ChatState) : null;

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
      {state?.live ? <p role="status">{liveNote(state.live)}</p> : null}
      {error && ERRORS[error] ? <p role="alert">{ERRORS[error]}</p> : null}
      <section aria-label="Conversation">
        {view.messages.length === 0 ? <p>Ask about returns, shipping, warranty, or your orders.</p> : null}
        <ol>
          {view.messages.map((message, index) => (
            <li key={index}>
              <strong>{speaker(message)}:</strong> {message.text}
            </li>
          ))}
        </ol>
      </section>
      {state?.offer === "leave_message" ? (
        <section aria-labelledby="leave-message">
          <h2 id="leave-message">Leave a message for a specialist</h2>
          <p>These replies have not helped. Leave a message, and a specialist will reply in this chat.</p>
          <form action={leaveAction}>
            <label>
              Message for a specialist
              <textarea name="message" required maxLength={2000} />
            </label>
            <button type="submit">Leave message</button>
          </form>
        </section>
      ) : null}
      <form action={sendAction}>
        <label>
          Your message
          <textarea name="question" required maxLength={2000} />
        </label>
        <button type="submit">Send</button>
      </form>
      {state?.live_enabled && !state.live ? (
        <form action={liveAction}>
          <button type="submit">Talk to a person</button>
        </form>
      ) : null}
      {state?.live ? <Refresh renew={renewAction} /> : null}
      <form action={endAction}>
        <button type="submit">End chat</button>
      </form>
    </main>
  );
}
