import { auth } from "@/auth";
import { redirect } from "next/navigation";

import { Refresh } from "../../../refresh";
import { apiUrl, sameSite } from "../../../same-site";
import { accessToken } from "../../access-token";

// One live chat (issue #138): the conversation as the customer sees it, a reply form, and the ending.
type LiveChat = {
  id: string;
  case_id: string;
  customer: string;
  messages: { role: string; name?: string; text: string }[];
};

const ID = /^[0-9a-f-]{36}$/;

function speaker(message: LiveChat["messages"][number]): string {
  if (message.role === "user") {
    return "Customer";
  }
  return message.role === "specialist" ? `${message.name}, specialist` : "Agent";
}

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

async function endAction(formData: FormData) {
  "use server";
  const { id, access } = await liveId(formData);
  const escalate = formData.get("outcome") === "escalate";
  const ended = await fetch(`${apiUrl}/live/${id}/${escalate ? "escalate" : "resolve"}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access}`, "Content-Type": "application/json" },
    body: escalate ? JSON.stringify({ note: String(formData.get("note") ?? "") }) : undefined,
  });
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
      {error ? <p role="alert">That message was not sent. Try again.</p> : null}
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
