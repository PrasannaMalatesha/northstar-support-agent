# Product requirements

Northstar Support Agent. Status: design. Owner: Malatesha. Brand: Northstar Goods, a fictional direct-to-consumer goods company.

This document says what the product is and what it must do. It does not choose libraries, schemas, or deploy steps. Those belong in `trd.md`, which is written only when asked.

If this file and `AGENTS.md` disagree about a feature, this file wins for product scope and `AGENTS.md` wins for how the agent is built.

## Problem

Support staff answer the same policy questions, look up orders, and decide refunds under time pressure. A general chatbot invents rules. A refund button with no review moves money too early. Staff need a colleague that reads the company handbook, shows its sources, and stops before any refund, credit, exchange, or cancellation is recorded.

## Product goal

A staff console where a support person can hand a customer conversation to the agent and get a grounded reply, a clear next action, and a human gate on anything that changes money or fulfillment.

Success is not a perfect score. Success is that a reviewer can see why the agent answered, which policy it used, which tools it called, and where it still fails.

## Users

| User | What they need |
| --- | --- |
| Support specialist | A draft reply, the policy excerpt, the order facts, and a proposed action |
| Support lead | A queue of proposed refunds and other gated actions, with enough context to approve, edit, or reject |
| Policy owner | A list of questions the agent could not answer from the handbook, so the handbook can be fixed |
| Reviewer of this project | A running demo, traces, and an evaluation story |

The end customer does not use this product directly in the first release. The specialist pastes or types the customer’s words. A customer-facing chat is a later release.

## Goals

- Answer company questions only from the written handbook, with citations.
- Look up order state from the order system, and never invent an order.
- Propose refunds, partial credits, exchanges, and cancellations. Record them only after a person approves.
- Refuse abuse, jailbreaks, and requests that are outside the handbook.
- Remember the conversation on a case, and remember a few durable customer facts across cases, without treating those facts as policy.
- Show staff when the agent is unsure.
- Measure answer quality, the path the agent took, safety, and cost before and after changes.

## Non-goals

- Charging a card, calling a bank, or moving real money.
- Diagnosing product defects from photos.
- Replacing the specialist. The agent drafts and proposes.
- Searching the public web for policy.
- Acting as legal counsel on chargebacks. It escalates those.
- A customer login or a storefront. (The slice 3 chat identifies a customer by order id and order email, with no account; see P2.)

## Sources of truth

| Source | What it decides |
| --- | --- |
| Handbook | Return window, eligibility, shipping, warranty, cancellations, exchanges, privacy, escalation |
| Order record | What this customer bought, when, for how much, fulfillment state, prior refunds |
| Catalog | What Northstar sells. A catalog answer that is not in this list is an abstain |
| Human decision | Whether a proposed money or fulfillment action is recorded |
| Case thread | What was said in this conversation |
| Customer memory | Preferences already given, such as “prefers email”. Never a substitute for the handbook |

If the handbook is silent, the agent asks for a missing fact or escalates. It does not fill the gap.

## How a case works

1. The specialist opens a case by looking up the customer by email or phone, then supplies the customer’s message, and an order id when they have one. The agent never chooses the customer. If no customer is found, the case opens without one. Handbook and catalog questions still work. Anything about an order is refused with “pick a customer first”. Customers are not created from the console.
2. The agent classifies the request.
3. It reads the handbook and, when needed, the order.
4. It returns a customer-facing draft, an internal rationale, citations, and a proposed action.
5. If the action changes money or fulfillment, the case waits. A lead approves, edits, or rejects.
6. Approval records a ticket. Rejection records the reason and does not.
7. The specialist can edit the draft before sending it to the customer through their usual channel. The console saves both the agent’s draft and the specialist’s final text on the case.
8. The specialist marks the case Resolved, or the agent’s escalation marks it Escalated.

Case status: **Open**, then **Waiting for approval** while a gated proposal is pending, then **Resolved** or **Escalated**. Resolved and escalated cases are read-only. A follow-up from the same customer opens a new case, which appears in that customer’s history.

## Features

Priority is the order of delivery. P0 is the first build. P1 and P2 are part of the product and are specified here so the technical document does not invent them later.

### P0 — first build

**Identity on the case.** The case is bound to one customer chosen by the specialist from a lookup by email or phone. The agent reads only orders owned by that customer. An order id that belongs to someone else is reported as “not found for this customer”, with no details about the other order. This also covers gated actions: no proposal is made on an order the case customer does not own.

**Order status.** Given an order id that belongs to the case customer, the agent reports status, order lines, purchase date, and prior refunds from the order record. It does not invent tracking events that are not on the record.

**Catalog answers.** Questions about what Northstar sells are answered only from catalog rows: name, category, price, sizes or variants, in stock yes or no, and final-sale flag. If the item is not in the catalog, or the question needs a field the row does not have (material, dimensions, delivery date for that item, reviews), the agent abstains. It does not describe a product from general knowledge. Stock is a yes or no from the row, not a count or a promise to hold the item.

**Handbook answers.** Questions on any handbook topic are answered by retrieving the handbook: company and what Northstar sells, returns and refunds, exchanges, shipping and delivery, warranty, order changes, payments and pricing, promotions and gift cards, privacy, escalation, and general FAQ (hours, contact, account). This is information only. An action such as a cancel or an exchange keeps its own priority. Every factual claim cites a section. If the match is weak, or the question is not in the handbook, the draft abstains and names what to ask next.

**Refund and partial credit.** The agent proposes approve, partial credit, or deny, with an amount that does not exceed the order and that follows the handbook. The proposal waits for a person. Approve or edit creates a ticket. Reject does not.

**Missing information.** If a refund needs an order id, a reason, or another required fact, the agent asks for it and does not guess.

**Already refunded.** If the order record says the item was already refunded, the agent does not propose a second refund. It says so and cites the record.

**Escalation and clarification.** Abuse that is not a simple slur, legal or chargeback language, and ambiguous policy conflicts become an escalation with a short handoff: what the customer asked, what the handbook says, what is missing.

**Safety.** Slurs and jailbreaks get a fixed safe reply, not a debate. Personal data is minimized in the customer draft. Secrets are blocked. The agent cannot call tools outside its allowed set.

**Case memory.** The thread keeps the conversation so a follow-up (“what about shipping?”) stays on the same case. Closing the laptop does not drop a refund that is waiting for approval.

**Customer history.** Every case is saved under its customer. When a new case opens, the agent sees a short record of that customer’s past cases: case ids, status, outcomes, open or completed tickets, and refunded lines. It does not see old transcripts. Stated preferences join this record in P1, with customer memory. The record can stop a duplicate refund. It cannot set an amount or override the handbook. Staff see the same record as a read-only history panel on the case desk: the customer's 5 most recent cases with id, status, outcome, and refunded lines. On an unbound case the panel is empty.

**Staff console.** Three screens: login, the case desk (chat, citations, the proposal and its controls, and the history panel), and the lead's waiting for approval list. It is hosted online for each environment and meets WCAG 2.2 AA.

**Waiting for approval list.** A lead sees a simple list of proposals waiting for a decision: case, action, amount, and how long it has waited. Stale rows are marked. Clicking a row opens the case desk, where the lead decides. Deciding directly from the list belongs to the P1 approval queue.

**Staff login.** Each staff member signs in with their own email and password. Accounts are created by an admin. Repeated wrong passwords lock the account briefly. Sessions expire, and logout ends them. Every login and every approval decision is recorded.

**Fair use.** Request rates and a daily model budget are limited per staff member. When a limit is reached, the console says so plainly and the case is not lost.

**Two roles.** Specialist and lead are separate demo logins. A specialist opens cases and edits drafts. Only a lead sees approve, edit amount, and reject. The person who proposed (the specialist on the case) cannot approve that proposal. Each decision records who made it and when.

**Stale proposals.** A proposal waiting more than 24 hours is shown as stale on the case desk. It is never approved or rejected automatically.

**Trust display.** The specialist sees the cited sections and whether the match was strong or weak. They are not asked to trust a bare paragraph.

**Quality program.** A labeled set of normal cases, edge cases, and failures. Checks for the action, the route, the path, the citations, and the approval gate. A judge for whether the wording matches the expected answer and whether it stays on the cited text. The same cases run before and after a change. Live traffic is sampled. Failures can be added to the labeled set.

Slice 1 labeled set: about 40 cases. Roughly 60% normal, 25% edge, 15% failure or adversarial. Split into 10 for calibrating the judge against human labels, 15 for development, and 15 held out for the release bar. A case is never moved between splits after its first use.

### P1 — same product, after P0 holds

**Cancellation of an unshipped order.** Propose cancel only when the handbook and the order state allow it. Same human gate as a refund.

**Address change.** Propose an address change only inside the handbook window and only before shipment. Human gate, because it changes fulfillment.

**Exchange instead of refund.** When the customer wants a different size or item, propose an exchange using the handbook. Human gate. Do not pretend stock was checked unless an order or catalog tool actually returned stock.

**Warranty claim draft.** Collect what the handbook requires for a claim and draft it. A person submits it. The agent does not tell the customer the claim is approved.

**Lost or delayed shipment.** Combine the order’s fulfillment state with the shipping section. Tell the specialist the next step the handbook allows (wait, investigate, replace, refund). Do not invent a carrier scan.

**Duplicate and open-ticket check.** If a ticket for the same order and action is already open or completed, the agent says so instead of opening another.

**Approval queue.** A lead sees waiting proposals across cases: customer ask, amount, citations, order summary, and approve / edit / reject.

**Handoff packet.** Escalation produces a packet a teammate can read without the whole thread: question, order id, citations, what was already tried, and the recommended owner (support lead, policy, or legal).

**Specialist corrections.** When a specialist edits the draft or the amount, store the before and after. Those pairs are candidates for the labeled evaluation set. They are not silently treated as new policy.

**Handbook gaps.** Questions that ended in abstain are listed for the policy owner: the question, the weak sections that were retrieved, and how often it happened.

**Customer memory across cases.** Remember non-sensitive preferences the customer already stated, such as contact channel. Do not store payment numbers. Do not let this memory override the handbook.

### P2 — later, still specified

**Customer-facing entry.** The same agent behind a customer chat, with the same gates. Not in the first build, because the user of record today is staff.

How a customer is identified (decided for slice 3): the customer enters an order id and the email on that order, as on an order-lookup form. There is no account and no password, so this is not the customer login the non-goals rule out. A match opens a short chat session for that one customer. A miss gets one message that does not say whether the order or the email was wrong, and repeated misses lock out for a while. The customer reads only orders they own. Every gated action is a proposal for a lead, and the customer is told it is waiting, not approved. The customer sees only the checked reply, never the draft, the amount, the internal rationale, or a handoff packet.

**Damaged-item photos.** Accept an image, describe it, and attach it to a claim. Not in the first build. Text descriptions of damage are in P0, judged against the damage section of the handbook.

**More than one language.** The handbook is English in the first build. Translation is a later release and must still cite the English section it used.

**Real payments and carrier APIs.** Out of the demo. The product shape leaves a gate where those systems would sit. The demo uses a mock order book and mock tickets.

**Single sign-on.** Slice 1 uses real staff accounts with email and password. SSO replaces password login later.

### Update phase — production readiness and live human support

Slices 1 to 3 are built. The update phase makes the product safe to run for real customers and adds a person behind the customer chat. It is planned, not started. It is grilled before any ticket is opened. The technical plan is `docs/plans/update-phase.md`.

**Bounded agent.** Every model call has a time limit and a fixed number of attempts. Every graph run has a step cap. A conversation that keeps failing stops and offers a person instead of trying again. A slow turn drops optional steps, such as rewording or translation, rather than running past its deadline. The first part (timeouts, attempts, step caps) is done in #128.

**Fair limits per customer.** Each chat customer has their own daily model budget and request limit, so one customer cannot use up the chat for everyone. Limits live in the database, so they survive a restart and hold across server processes.

**Escalations are picked up.** Every escalated case, from the desk or the chat, appears in a staff inbox with its handoff packet. The promise "a specialist will follow up" has a place where that happens.

**Talk to a person.** In the customer chat, the customer can ask for a person. The agent can also hand over: after an escalation, or after a run of turns it could not resolve. The customer joins a line, sees their place and an estimated wait as a range, and can go back to the agent at any time. When the wait is too long or no one is online, the customer can leave a message instead, and it goes to the escalations inbox.

**Specialists take live chats.** A specialist marks themselves available and takes up to a set number of chats at once. A chat is offered to the specialist with the most spare capacity, and they accept it within a short window. A chat that is not accepted goes to the next specialist. While a person is in the chat, the agent does not reply. The specialist sees the conversation so far, the customer's orders, and their past cases.

**People still approve money.** A refund, cancel, exchange, address change, or warranty claim raised in a live chat is still a proposal for a lead. The specialist who raised it cannot approve it.

**Quiet customers free the specialist.** If the customer stops replying, the chat is nudged, then set aside so the specialist can take the next customer, then closed. A customer who comes back returns to the same specialist when they can, with the conversation kept.

**Quality measured within budget.** Experiments are sized to stay inside the monthly LangSmith trace allowance. The release bar's latency and token gates are measured on real runs and enforced before `uat`.

## Requirements

Each requirement has an acceptance check a person can observe. Identifiers are stable so `trd.md` can point at them.

| ID | Requirement | Acceptance | Priority |
| --- | --- | --- | --- |
| R1 | Handbook answers cite real sections | A policy answer shows one or more section ids that exist in the handbook. A claim with no section is not shown as fact | P0 |
| R2 | Silence abstains | A question the handbook does not cover asks a follow-up or escalates. It does not invent a rule | P0 |
| R3 | Order facts come from the order | Status, dates, and amounts match the order record for that id. An unknown id is reported as unknown | P0 |
| R4 | Refunds wait | No refund ticket exists until a person approves or edits the proposal | P0 |
| R5 | Amounts stay inside the order and the handbook | The proposed amount is not above the order total and matches the handbook rule used | P0 |
| R6 | Second refund is refused | An already-refunded line is not proposed again | P0 |
| R7 | Missing facts are requested | A refund without an order id asks for the id and does not create a proposal that depends on it | P0 |
| R8 | Abuse is a fixed reply | A slur or jailbreak does not get a policy essay or a tool call that changes a ticket | P0 |
| R9 | Personal data is minimized | The customer draft does not repeat a full payment number, and email or phone is masked or removed unless the specialist needs it to act | P0 |
| R10 | The case survives a restart | A waiting approval is still waiting after the API process restarts, on the same case | P0 |
| R11 | Staff can see why | The console shows the draft, the rationale, the citations, and the proposed action | P0 |
| R12 | Quality is measured before ship | A change that misses any number in the release bar does not deploy | P0 |
| R13 | Cancel, address change, and exchange use the same gate | Those actions are proposed from the handbook and recorded only after approval | P1 |
| R14 | Orders are scoped to the case customer | An order id not owned by the case customer returns “not found for this customer” and no proposal | P0 |
| R15 | Open tickets are visible | A second proposal for the same order and action is blocked or explicitly flagged | P1 |
| R16 | Leads have a queue | Waiting items can be approved, edited, or rejected without opening each chat first | P1 |
| R17 | Escalations are portable | The handoff packet stands alone | P1 |
| R18 | Edits are kept | A specialist’s edit of a draft or amount is stored with the original | P1 |
| R19 | Gaps are listed | Abstained questions are listed with the sections that were retrieved | P1 |
| R20 | Cross-case memory is not policy | A stored preference can be used in tone or channel. It cannot set a refund amount | P1 |
| R21 | Catalog answers use catalog rows only | A question about what Northstar sells names only catalog items and only the fields on the row. An unknown item or missing field is an abstain | P0 |
| R22 | Only a lead approves | A specialist login has no approve control. The proposer cannot approve their own proposal | P0 |
| R23 | Stale proposals are flagged, not decided | A proposal older than 24 hours shows as stale and stays waiting | P0 |
| R24 | Only signed-in staff reach the agent | Every API call without a valid session is refused. No public sign-up exists | P0 |
| R25 | Logins resist guessing | Five wrong passwords in 15 minutes lock that login, and the attempt is recorded | P0 |
| R26 | Usage is bounded | Request rates and a daily model budget per staff member are enforced, with a clear message when reached | P0 |
| R27 | Secrets never reach the browser | No model, database, or backend token is visible in browser code, storage, or network responses | P0 |
| R28 | Leads can find waiting proposals | A lead login shows every pending proposal in one list, with its age and stale flag | P0 |
| R29 | A case without a customer cannot touch orders | On an unbound case, order questions get “pick a customer first” and no order tool runs | P0 |
| R30 | Closed cases stay closed | Resolved and escalated cases accept no new messages or proposals | P0 |
| R31 | Final text is kept | The agent’s draft and the specialist’s final text are both saved on the case | P0 |
| R32 | The console is accessible | Every screen passes automated WCAG 2.2 AA checks and can be used by keyboard alone | P0 |
| R33 | Staff see the customer's past cases | The case desk shows a read-only panel with the customer's 5 most recent cases (id, status, outcome, refunded lines). It is empty on an unbound case | P0 |
| R34 | Every model call is bounded | Each model request times out, and each call makes a fixed, small number of attempts. Each graph run has a step cap below the library default. Done in #128 | U |
| R35 | A failing conversation stops | After a set number of turns in a row that end in a clarification, an abstain, or a failed lookup, the agent stops trying and offers a person | U |
| R36 | A turn has a deadline | A turn that runs short of time skips optional steps and still returns a checked reply. No turn waits on a model with no limit | U |
| R37 | Chat limits are per customer | One chat customer reaching their daily budget or request limit does not stop another customer. Limits hold after a restart | U |
| R38 | Escalations have an inbox | Every escalated case appears in a staff list with its handoff packet, from the desk and from the chat | U |
| R39 | A customer can ask for a person | The chat has a control to talk to a person. Using it puts the customer in the line and says so | U |
| R40 | The wait is shown honestly | A waiting customer sees their place and an estimated wait as a range. With too little history, the chat says so instead of showing a number | U |
| R41 | No endless line | When the estimate is over the cap or no specialist is online, the customer is offered to leave a message instead of joining the line | U |
| R42 | One customer, one specialist | A waiting customer is offered to one specialist at a time. No specialist gets more chats than their capacity. Concurrent assignment never gives one customer to two people | U |
| R43 | Unaccepted chats move on | A chat not accepted within the window goes to the next specialist. A customer is offered a set number of times before the leave-a-message option. A specialist who misses offers in a row is set to away | U |
| R44 | Quiet customers free the specialist | With no customer reply, the chat is nudged, then set aside so the specialist's slot is free, then closed. A returning customer goes back to the same specialist when they can | U |
| R45 | Live chats keep the approval gate | A gated action raised in a live chat becomes a proposal in the lead's queue. The specialist who raised it cannot approve it | U |
| R46 | A person's replies are checked | A specialist's chat message is screened for personal data before the customer sees it, and it is audited. The agent does not reply while a person holds the chat | U |
| R47 | The chat survives the wait | A customer waiting for or talking to a person is not signed out of the chat mid-conversation | U |
| R48 | Quality is measured within budget | One full experiment round fits inside the monthly trace allowance with room left. Latency and token gates are computed from real runs and checked before `uat` | U |
| R49 | Leads see the line | A lead sees specialists online, the line length, the longest wait, and the average chat length | U |

## Experience

The specialist’s main screen is a case desk. The customer’s words are on the left. The draft, cited handbook sections, order lines, and the proposed action are on the right. Approve, edit, and reject are separate controls. The desk is quiet: paper colors, one accent reserved for approval. Reject asks for a short reason.

In slice 1, the lead’s “Waiting for approval” list shows the action, the amount, the order id, and how long each item has waited. Rows open the case desk. In slice 2, the queue lets the lead decide from the list.

While the agent works, the desk shows its steps as they happen: classifying, reading the handbook, looking up the order. The draft appears all at once, only after the safety check has passed. The specialist never sees draft text that is later withdrawn.

Empty state: no order id yet, the draft says what to ask. Error state: the order system or the handbook search failed, the draft says the lookup failed and does not fill in facts. The specialist can retry.

### Visual hierarchy

The case desk reads in a fixed order of importance:

1. **Decision.** The proposal card (action, amount, handbook rule, order line) and its controls. The only place the accent color appears.
2. **Evidence.** The draft, then the citation cards (section id, title, strong or weak match). At most 4 cards.
3. **Context.** The customer's message, the order lines, and the history panel.
4. **Process.** Streamed steps, case status, timestamps.

### UX laws applied

Source: [Laws of UX](https://lawsofux.com/).

| Law | How the console applies it |
| --- | --- |
| Jakob's Law | Two-pane desk like common helpdesk tools. Standard email and password login |
| Hick's Law, Choice Overload | A lead sees three decision controls: approve, edit amount, reject. A specialist sees none |
| Fitts's Law | Decision controls are at least 24 by 24 CSS pixels and sit inside the proposal card. Reject is spaced apart from approve |
| Von Restorff Effect | One accent, reserved for waiting for approval. Stale gets a distinct badge, not a second accent |
| Proximity, Common Region | Each citation and each proposal is one bordered card |
| Miller's Law, Chunking | History shows 5 cases. Evidence shows at most 4 citations |
| Doherty Threshold | The first step indicator appears within 400 ms of sending |
| Tesler's Law | Customer scoping, policy math, and amount checks live on the server, not with the specialist |
| Postel's Law | Customer lookup accepts email or phone in common formats |
| Peak-End Rule | Approval ends with a clear confirmation and the ticket id. A Resolved case shows its final state |
| Zeigarnik Effect | The waiting list shows a count. Open cases show a status chip |
| Mental Model | Status labels are exactly Open, Waiting for approval, Resolved, Escalated |
| Paradox of the Active User | No tutorial. Empty and error states say the next step inline |
| Aesthetic-Usability Effect | Quiet paper palette |

### Accessibility

The console meets WCAG 2.2 AA ([what is new in 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)): keyboard use for every control, a visible focus that is never hidden (2.4.11), targets of at least 24 by 24 CSS pixels (2.5.8), and login that allows paste and password managers (3.3.8). Streamed steps are announced to screen readers.

## Safety and permission

| Action | Who may complete it |
| --- | --- |
| Answer from the handbook | Agent, if citations exist |
| Look up an order | Agent |
| Propose refund, credit, exchange, cancel, address change, warranty claim | Agent |
| Record those proposals | A person, after review |
| Escalate | Agent may recommend. A person owns the handoff |
| Change the handbook | A policy owner, outside this agent |

The agent is not a policy author. Specialist edits train evaluation examples. They do not rewrite the handbook by themselves.

## Privacy

Collect the minimum needed to answer the case. Do not put payment instruments in the handbook index or in long-term memory. Customer memory is per customer and is limited to preferences, not credentials. Staff log in with their own accounts. There is no public sign-up. Each staff member has a daily model budget, and request rates are limited so no one, inside or outside, can run up the model bill. Production later moves to staff SSO.

## Measures

| Measure | What good looks like |
| --- | --- |
| Task outcome | The action and the reply match the labeled case |
| Path | The agent read the handbook before a policy claim, and looked up the order when an order id was present |
| Permission | Gated actions have an approval. Ungated answers do not create tickets |
| Grounding | Citations exist and the reply does not contradict them |
| Operability | Latency, token cost, step count, and error rate stay within the release bar |
| Usefulness to staff | Specialists accept or lightly edit drafts more often than they rewrite them. This is observed, not assumed |

### Release bar

Measured on the test split of the labeled set. Any miss blocks the release.

| Gate | Threshold |
| --- | --- |
| Action correct | At least 80% of rows |
| Ticket without approval | Zero |
| Invalid citation (section id not in the handbook) | Zero |
| Abstain rows (outside the handbook, unknown catalog item, missing field, order not owned) | Every one abstains |
| Latency | p95 under 10 seconds per turn, excluding time waiting for approval |
| Token budget | No call exceeds its cap in `AGENTS.md` |

Perfect scores are not the goal. Known failures are listed with the case that shows them.

## Release slices

| Slice | Includes | Excludes |
| --- | --- | --- |
| 1 | P0 features, synthetic customers, orders, and catalog, mock tickets, staff console with specialist and lead logins, evaluation on the labeled set | P1 queue, SSO, real payments, photos, customer-facing chat |
| 2 | P1 features | P2 |
| 3 | P2 only after slice 2 is in use | |
| Update phase | R34 to R49: bounded agent, fair limits, escalations inbox, live human chat, quality within budget | Real payments, voice, a customer login |

Slice 1 is what the first implementation builds. Slice 2 and slice 3 stay in this document so they are not redesigned from scratch.

## Handbook the product depends on

The handbook is written by this project before the agent runs, as the first phase of the build. It is version `northstar-policy-v2`, for a US store selling apparel and footwear, bags and accessories, home and kitchen, and small electronics. The topics follow common marketplace practice: category return windows, item condition, final sale, damage on arrival, exchanges, shipping times and costs, warranty, cancellation before shipment, payments, price adjustments, promotions, gift cards, privacy, and escalation. The words are Northstar’s. Pages from Amazon, Flipkart, or any other company are not copied in. The agent does not draft new handbook sections when it is unsure. Each section has a stable id. The labeled cases cite those ids.

Order records used in the demo are synthetic.

## Risks

| Risk | What we do about it |
| --- | --- |
| The agent sounds right and is wrong | Citations, abstain on a weak match, and a grounding check |
| A refund is recorded too early | Human gate, tested as a hard failure |
| Staff over-trust the draft | Show the section and the match strength |
| The labeled set drifts from real tickets | Add failed live cases and specialist edits back into the set |
| Scope grows past a reviewable demo | Slice 1 is P0 only |
| A model hangs or a loop runs away | Time limits, fixed attempts, step caps, and a stop after repeated failed turns (R34 to R36) |
| Evals use up the trace allowance | Experiments sized to the monthly budget (R48) |
| Customers wait with no one coming | Honest estimates, a cap, and leave-a-message (R40, R41) |
| A live chat moves money without review | The lead approval gate holds in live chats (R45) |

## Open points

These are product choices still open. They are not technical designs.

Update phase settings, proposed and not yet agreed:
- Chats per specialist at once: 2.
- Window to accept an offered chat: 45 seconds. Offers per customer before leave-a-message: 3. Missed offers in a row before a specialist is set to away: 2.
- Quiet customer: nudge at 2 minutes, slot freed at 3 minutes, chat closed at 15 minutes.
- Longest estimated wait before leave-a-message: 20 minutes.
- Turns in a row without progress before the agent offers a person: 3.
- Support hours: not defined.
- Whether leads also take live chats, or only approve.
- A separate LangSmith account with a fresh monthly allowance for the demo, later.

Closed:
- Partial credit is 50% store credit only (REF-PARTIAL).
- Stale flag at 24 hours.
- Only a lead approves.
- The exchange section is written in handbook v2 (EXC-*).
- Lead approvals come from a simple waiting list.
- Unbound cases are allowed for handbook and catalog questions only.
- Case status is Open, Waiting for approval, Resolved, or Escalated.
- Staff see the customer history as a read-only panel (R33).
- The console meets WCAG 2.2 AA (R32).

Any feature not in this document is out of scope until it is added here first.

## Document map

| Document | Role |
| --- | --- |
| `prd.md` | This file |
| `AGENTS.md` | Build contract |
| `architecture.md` | Picture of the system |
| `explanation.md` | Why the decisions were made |
| `correction.md` | Later changes and defects |
| `CONTEXT.md` | Glossary |
| `docs/spec.md` | Implementation spec for slice 1 |
| `docs/plans/phase-0-handbook-v2.md` | Handbook v2 plan |
| `docs/plans/slice-1-build-phases.md` | Build phases and requirement mapping |
| `docs/plans/update-phase.md` | Update phase plan: bounded agent, live human chat, quality within budget |
| `trd.md` | Not written yet |
