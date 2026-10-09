# The live chat line runs in Postgres, and the agent only decides to hand over

Status: accepted (2026-10-09)

Live chat requests wait in a Postgres table. One assignment function claims the next request with `SELECT ... FOR UPDATE SKIP LOCKED`, and the live chat itself is rows in that table and in `case_messages`. The agent's only part is deciding to hand over: an escalation, or the "Talk to a person" offer after three failed turns. We chose Postgres because it already holds cases, tickets, and the LangGraph checkpoints, and the Postgres docs describe `SKIP LOCKED` for queue-like tables with many consumers. A message broker would add a service to run for a few dozen chats an hour. We do not keep a LangGraph run paused for the length of a human conversation. An interrupt waits for one resume value and re-runs its node on resume, which fits the lead's single approval decision (where the code uses it today), not many messages over minutes or hours.

## Considered options

- **Redis or a message broker for the line.** Rejected for now: another service, another secret, and the line's state would sit apart from the cases it belongs to.
- **A LangGraph interrupt per live chat.** Rejected: one long paused run per chat, node re-execution on every resume, and the checkpointer as the store of a human conversation.

## Consequences

- The line, presence, and limits are database rows, so they survive a restart and hold across server processes. The in-memory request counter is moved to the database for the same reason.
- At much higher volume, the line can move to a broker behind the same assignment function without touching the agent.
