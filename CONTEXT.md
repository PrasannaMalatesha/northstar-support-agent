# Northstar support

The language of a support case at Northstar Goods: a customer bought something, a specialist handles the case, and the handbook is the only company rule.

## Language

**Customer**:
The person who bought from Northstar Goods.
_Avoid_: User, client, shopper, account

**Specialist**:
The staff member who works a case in the console.
_Avoid_: Agent (the person), rep, user

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
