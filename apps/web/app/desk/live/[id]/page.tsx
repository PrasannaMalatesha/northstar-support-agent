import { auth } from "@/auth";
import { redirect } from "next/navigation";

import { Refresh } from "../../../refresh";
import { apiUrl, sameSite } from "../../../same-site";
import { accessToken } from "../../access-token";

// One live chat (issue #138): the conversation as the customer sees it, a reply form, and the ending.
// The specialist also raises money actions here, and only they see those turns (issue #143).
type LiveChat = {
  id: string;
  case_id: string;
  customer: string;
  messages: { role: string; name?: string; text: string }[];
  // The status line the customer sees, such as "Nothing is approved yet".
  status: string;
  spanish: boolean;
  // The agent's handoff when its escalation joined the line, else empty (issue #141).
  handoff: string;
};

const ID = /^[0-9a-f-]{36}$/;

const SPEAKERS: Record<string, string> = {
  user: "Customer",
  action: "Your action, not shown to the customer",
  desk: "Desk rules, not shown to the customer",
};

function speaker(message: LiveChat["messages"][number]): string {
  if (message.role === "specialist") {
    return `${message.name}, specialist`;
  }
  return SPEAKERS[message.role] ?? "Agent";
}

const ERRORS: Record<string, string> = {
  unsent: "That message was not sent. Try again.",
  unraised: "That action was not raised. Try again.",
  waiting: "A proposal on this live chat is waiting for a lead. The chat ends, or takes another action, once a lead decides.",
};

async function liveId(formData: FormData): Promise<{ id: string; access: string }> {
  const id = String(formData.get("id") ?? "");
  if (!(await sameSite()) || !ID.test(id)) {
    redirect("/desk");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  return { id, access };
}

async function sendAction(formData: FormData) {
  "use server";
  const { id, access } = await liveId(formData);
  const sent = await fetch(`${apiUrl}/live/${id}/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access}`, "Content-Type": "application/json" },
    body: JSON.stringify({ text: String(formData.get("text") ?? "") }),
  });
  redirect(sent.ok ? `/desk/live/${id}` : `/desk/live/${id}?error=unsent`);
}

// A refund, cancel, exchange, address change, or warranty claim, decided by the agent's own rules. A lead approves it.
async function raiseAction(formData: FormData) {
  "use server";
  const { id, access } = await liveId(formData);
  const raised = await fetch(`${apiUrl}/live/${id}/actions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access}`, "Content-Type": "application/json" },
    body: JSON.stringify({ text: String(formData.get("request") ?? "") }),
  });
  if (raised.status === 403) {
    redirect("/desk?live=gone");
  }
  redirect(raised.ok ? `/desk/live/${id}` : `/desk/live/${id}?error=${raised.status === 409 ? "waiting" : "unraised"}`);
}

async function endAction(formData: FormData) {
  "use server";
  const { id, access } = await liveId(formData);
  const escalate = formData.get("outcome") === "escalate";
  const ended = await fetch(`${apiUrl}/live/${id}/${escalate ? "escalate" : "resolve"}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access}`, "Content-Type": "application/json" },
    body: escalate ? JSON.stringify({ note: String(formData.get("note") ?? "") }) : undefined,
  });
  if (ended.status === 409) {
    redirect(`/desk/live/${id}?error=waiting`);
  }
  redirect(!ended.ok ? "/desk?live=gone" : escalate ? "/desk?live=escalated" : "/desk?live=resolved");
}

export default async function LiveChatPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const { id } = await params;
  const { error } = await searchParams;
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }
  const access = await accessToken();
  if (!access) {
    redirect("/login");
  }
  const response = await fetch(`${apiUrl}/live`, {
    headers: { Authorization: `Bearer ${access}` },
    cache: "no-store",
  });
  const chats = response.ok ? ((await response.json()) as { chats: LiveChat[] }).chats : [];
  const chat = chats.find((item) => item.id === id);
  if (!chat) {
    redirect("/desk?live=gone");
  }

  return (
    <main className="desk">
      <p className="quiet">
        {session.user.name} · {session.user.role}
      </p>
      <h1>Live chat with {chat.customer}</h1>
      <p className="quiet">
        Case {chat.case_id}. <a href="/desk">Back to my desk</a>
      </p>
      {chat.spanish ? (
        <p>
          <strong>Spanish</strong>. The customer writes in Spanish. Reply in Spanish yourself: nothing translates your
          words.
        </p>
      ) : null}
      {chat.status ? <p role="status">The customer sees: {chat.status}</p> : null}
      {chat.handoff ? (
        <section aria-labelledby="handoff">
          <h2 id="handoff">Handoff</h2>
          <p className="quiet">The agent escalated this chat. The customer does not see this.</p>
          <p className="handoff">{chat.handoff}</p>
        </section>
      ) : null}
      {error ? <p role="alert">{ERRORS[error] ?? ERRORS.unsent}</p> : null}
      <section aria-label="Conversation">
        <ol>
          {chat.messages.map((message, index) => (
            <li key={index}>
              <strong>{speaker(message)}:</strong> {message.text}
            </li>
          ))}
        </ol>
      </section>
      <form action={sendAction}>
        <input type="hidden" name="id" value={chat.id} />
        <label>
          Your reply
          <textarea name="text" required maxLength={2000} />
        </label>
        <button type="submit">Send</button>
      </form>
      <form action={raiseAction}>
        <input type="hidden" name="id" value={chat.id} />
        <label>
          Action for a lead
          <input
            name="request"
            type="text"
            required
            maxLength={2000}
            placeholder="Refund order NS-1001"
            aria-describedby="action-help"
          />
        </label>
        <p className="quiet" id="action-help">
          The handbook rules set the amount, and a lead approves it. The customer sees only that nothing is approved yet.
        </p>
        <button type="submit">Raise action</button>
      </form>
      <form action={endAction}>
        <input type="hidden" name="id" value={chat.id} />
        <button type="submit" name="outcome" value="resolve">
          Resolve
        </button>
      </form>
      <form action={endAction}>
        <input type="hidden" name="id" value={chat.id} />
        <input type="hidden" name="outcome" value="escalate" />
        <label>
          Handoff note
          <textarea name="note" required maxLength={2000} />
        </label>
        <button type="submit">Escalate</button>
      </form>
      <Refresh />
    </main>
  );
}
