# Northstar support

The language of a support case at Northstar Goods: a customer bought something, a specialist handles the case, and the handbook is the only company rule.

## Language

**Customer**:
The person who bought from Northstar Goods.
_Avoid_: User, client, shopper, account

**Specialist**:
The staff member who works a case in the console.
_Avoid_: Agent (the person), rep, user

**Agent**:
The AI that drafts replies and proposals for a case. It never approves a gated action and never stands in for a person.
_Avoid_: Agent (meaning a person), bot, assistant

**Lead**:
The only staff member who may approve, edit, or reject a gated action. Never the person who proposed it.
_Avoid_: Manager, admin

**Staff account**:
The login of one specialist or lead, created by an admin. Never a customer.
_Avoid_: User account, customer login

**Handbook**:
The written company rules for Northstar Goods. People on this project write it before any case is handled. A section id points at one rule. The agent retrieves it and does not add rules.
_Avoid_: Policy docs, knowledge base, corpus, when speaking about the product

**Order**:
One purchase by a customer, with lines, money, and fulfillment state.
_Avoid_: Purchase, transaction, cart

**Case**:
One support conversation about one customer matter.
_Avoid_: Thread, ticket, session, chat

**Proposal**:
The agent's recommended action, not yet recorded.
_Avoid_: Decision, when the action is still waiting

**Ticket**:
The record that a gated action was approved.
_Avoid_: Proposal, case

**Citation**:
A handbook section id that supports a claim in a draft.
_Avoid_: Source, link, when the claim is about company rules

**Abstain**:
The agent states that the handbook, the catalog, or the order does not support an answer.
_Avoid_: Hallucination, fallback, as the name of the behavior

**Handoff**:
A short packet that lets another person continue a case.
_Avoid_: Escalation ticket, when no ticket was recorded

**Catalog item**:
Something Northstar sells, with a name, category, price, sizes or variants, in stock yes or no, and whether it is final sale. Nothing else about it is known.
_Avoid_: Product, when the customer already bought it

**Order line**:
One catalog item on one order, with the quantity and the amount paid.
_Avoid_: Product, purchase

**Case customer**:
The one customer a specialist binds to a case by email or phone lookup. The agent reads only this customer's orders.
_Avoid_: Verified user, logged-in user

**Case status**:
Open, Waiting for approval, Resolved, or Escalated. Resolved and Escalated are read-only.
_Avoid_: Closed, done, archived

**Unbound case**:
A case with no case customer. Handbook and catalog questions only.
_Avoid_: Anonymous case, guest case

**Stale proposal**:
A proposal waiting more than 24 hours. Flagged, still waiting, never decided automatically.
_Avoid_: Expired proposal

**Case desk**:
The specialist's main screen for one case: the customer's words, the draft, citations, the proposal, and the history panel.
_Avoid_: Chat screen, dashboard

**History panel**:
The read-only list of the case customer's 5 most recent cases on the case desk. Empty on an unbound case.
_Avoid_: Customer profile, transcript history

**Waiting for approval list**:
The lead's list of every pending proposal with its age and stale flag. A row opens the case desk.
_Avoid_: Queue (the P1 approval queue decides from the list)

**Draft**:
The customer-facing reply shown to the specialist, beside the citations and the proposal.
_Avoid_: Answer, when it has not been sent

**Exchange**:
A swap of the same item for another size or color, still waiting for a person before it is recorded.
_Avoid_: Replacement, when the item was damaged or defective

**Replacement**:
The same item sent again because it was damaged or defective, and only when the catalog row says it is in stock.
_Avoid_: Exchange, when the customer wants a different size or color

**Store credit**:
Credit Northstar holds for that customer, with no expiry and no transfer to someone else. It is not cash and not a gift card.
_Avoid_: Refund, when the money goes back to the original payment method

**Live chat request**:
A customer's request, in the customer chat, to talk with a specialist. It waits in the line until a specialist accepts it.
_Avoid_: Handoff, transfer, ticket

**Live chat**:
A customer chat that a specialist has accepted. While it lasts, the specialist replies and the agent does not.
_Avoid_: Session, live agent chat

**Line**:
The live chat requests waiting for a specialist, in the order they will be offered.
_Avoid_: Queue (the approval queue is the lead's), backlog

**Escalations inbox**:
The staff list of escalated cases with their handoffs. Leads see all of them. A specialist picks one up to work it.
_Avoid_: Escalation queue, follow-up list

**Offer**:
One live chat request shown to one specialist, who accepts or declines it within a short window. An offer that is not accepted goes to the next specialist.
_Avoid_: Assignment, before the specialist accepts

**Available**:
A specialist who is signed in and ready to take live chats, up to their own number of chats at once. Otherwise they are away.
_Avoid_: Online, when the specialist has stepped away

**Left message**:
What a customer leaves when no specialist is available or the wait is too long. It becomes an escalated case, and the reply appears in that customer's chat.
_Avoid_: Ticket, email, voicemail

