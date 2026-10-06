# Phase 0: Northstar handbook v2

Status: planned, not started.

## Why first

The handbook is the only thing the agent's RAG may cite. Every labeled eval case, citation check, and refund rule points at its section ids. Writing it all at once and freezing it means the evals, the prompts, and the Pinecone ingest all build on something that won't move.

## Ground rules

- Original Northstar wording. Topics and number ranges follow published practice. Nothing is pasted from these pages:
  - [Amazon return policy](https://www.amazon.com/gp/help/customer/display.html?nodeId=GKM69DUUYKQWKWX7)
  - [Amazon refund timelines](https://www.amazon.com/gp/help/customer/display.html?nodeId=GKQNFKFK5CF3C54B)
  - [Amazon non-returnable items](https://www.amazon.com/gp/help/customer/display.html?nodeId=201077750)
  - [Flipkart category windows, via Zoutons](https://zoutons.com/news/flipkart-return-replacement-policy-2026)
  - [Target returns](https://www.target.com/help/articles/returns-exchanges/returns)
  - [Target price match](https://www.target.com/help/articles/policies-guidelines/price-match-guarantee)
  - [Zappos shipping and returns](https://www.zappos.com/c/shipping-and-returns)
  - [EVGA store policies](https://www.evga.com/legal/store/)
- One rule per section, so one section becomes one retrievable chunk. Every section uses the same template:
  - id and title as the heading
  - **Rule**: the policy itself
  - **Applies when**: the situations it covers
  - **Agent must not**: what the agent may never promise
  - **Example**: one worked case
- Every number appears in exactly one section. Other sections refer to that section id instead of repeating the number.
- The version moves to `northstar-policy-v2`. Ids from v1 are kept where the rule is the same, so nothing downstream breaks.

## Files under `data/policy/`

**`company-overview.md`** (new)
- CO-ABOUT: Northstar Goods is a US direct-to-consumer brand.
- CO-CATEGORIES: the four categories it sells.
- CO-SCOPE: what support can and cannot do, for example no in-store service and no international orders.

**`returns-and-refunds.md`** (rewrite of v1)
- REF-WINDOW and REF-CATEGORY: the window starts at delivery. Apparel, footwear, bags and home goods get 30 days. Small electronics get 15 days.
- REF-CONDITION: apparel unworn with tags on; electronics with all accessories.
- REF-ELIGIBILITY and REF-DENY: kept from v1.
- REF-PARTIAL: used items get 50% store credit, as in v1.
- REF-DAMAGED: report within 14 days for a full refund including shipping. Kept from v1.
- REF-WRONG-ITEM and REF-MISSING-ITEM: new.
- REF-FINAL-SALE: v1 list plus opened in-ear earbuds, unless they are defective.
- REF-METHOD: refund to the original payment method, or store credit if the customer chooses it.
- REF-TIMING: Northstar processes a return within 3 business days of receiving it. Then a card takes 3 to 5 business days, a debit card up to 10, and store credit within 24 hours.
- REF-SHIP-COST: free return label when Northstar is at fault. Otherwise a $6.00 label fee comes out of the refund. Store-credit returns are free.
- REF-GIFT: gift returns go to the recipient as store credit.
- REF-HOLIDAY: items bought Nov 1 to Dec 24 can be returned until Jan 31.
- REF-INSPECTION: what happens when a returned item does not match its stated condition.

**`exchanges.md`** (new)
- EXC-ELIGIBILITY: apparel, footwear and bags; same item, different size or color, same price; inside 30 days; unworn.
- EXC-STOCK: only when the catalog row says in stock. Otherwise the case becomes a refund.
- EXC-LIMIT: one exchange per order line.
- EXC-PROCESS: the replacement ships when the return is scanned. Shipping is free both ways.
- EXC-DIFFERENT-ITEM: a different item is handled as a return plus a new order.
- REP-REPLACEMENT: a damaged or defective item is replaced with the same item if it is in stock.

**`shipping-and-delivery.md`** (rewrite)
- SHIP-REGIONS: all 50 US states. No international shipping.
- SHIP-OPTIONS: standard shipping is free over $50, otherwise $5.95. Express is $14.95.
- SHIP-SLA: 1 business day to process, then standard 5 to 7 business days or express 2. Alaska and Hawaii add 3 days.
- SHIP-DELAY, SHIP-LOST, SHIP-ADDRESS: kept from v1.
- SHIP-SPLIT: orders that arrive in more than one package.
- SHIP-DNR: marked delivered but not received. Wait 48 hours, then the case escalates.
- SHIP-REFUSED: a refused package is treated as a return, and outbound shipping is not refunded.

**`warranty.md`** (rewrite)
- WAR-COVERAGE: electronics, home goods and bags are covered for 1 year. Apparel and footwear are covered for 90 days against manufacturing defects.
- WAR-EXCLUSIONS and WAR-CLAIM: kept from v1.
- WAR-REMEDY: repair, replace, or refund.
- WAR-RECALL: a safety recall always escalates and gets a full refund, regardless of the window.

**`order-changes.md`** (extend)
- ORD-CANCEL, ORD-MODIFY, ORD-TRACK: kept from v1.
- ORD-PARTIAL-CANCEL: cancel one line while the order is still in status placed.

**`payments-and-pricing.md`** (new)
- PAY-METHODS: Visa, Mastercard, Amex, Discover, PayPal, Apple Pay, Google Pay and Northstar gift cards. No cash on delivery and no checks.
- PAY-CHARGE-TIMING: the card is authorized at order and charged at shipment.
- PAY-TAX: sales tax follows the ship-to address.
- PAY-PRICE-ADJUST: a price drop within 14 days of delivery is refunded as the difference, once per line. Clearance, final sale and flash deals are excluded.
- PAY-PRICE-ERROR: Northstar may cancel an order with a pricing error before it ships, with a full refund.
- PAY-DUPLICATE: a duplicate pending authorization hold drops off within 3 to 5 business days. A charge that actually posted twice escalates.

**`promotions-and-gift-cards.md`** (new)
- PROMO-CODES: one code per order, and it cannot be added after the order is placed.
- PROMO-RETURNS: the refund is the amount actually paid after discounts. Bundle discounts are prorated across lines.
- PROMO-THRESHOLD: if a return drops an order below the $50 free-shipping threshold, shipping is not charged back.
- GC-TERMS: gift cards have no expiry and no fees. They are not redeemable for cash except where law requires.
- GC-LOST: a lost gift card is replaced only if it was registered to the account.
- STORE-CREDIT: store credit has no expiry and is not transferable.

**`support-escalation.md`** (extend)
- ESC-WHEN, ESC-ABUSE, ESC-LEGAL: kept from v1.
- ESC-FRAUD: suspected account takeover or a fraudulent order escalates.

**`privacy-and-pii.md`** (extend)
- PII-MINIMIZE, PII-SHARE: kept from v1.
- PII-PAYMENT: never ask for a full card number.
- PII-DELETE: a data deletion request goes to the privacy team, which responds within 45 days.

**`faq-general.md`** (extend)
- FAQ-HOURS, FAQ-CONTACT, FAQ-ACCOUNT: kept from v1.
- FAQ-PASSWORD: password resets use the sign-in link.
- FAQ-EMAILS: how to unsubscribe from marketing email.
- FAQ-SIZING: size questions are answered only from the catalog row. Fit advice abstains.

**`SECTION_IDS.md`**: the registry of every id. Each line has the id, the file, a one-line rule summary, and whether it is unchanged from v1 or new.

## Conflict checks before freezing

- The damage report window (14 days) is shorter than the shortest return window (15 days for electronics). That is intentional and stated in REF-DAMAGED.
- Exchange and refund windows match per category.
- Warranty never overlaps the return window in a way that gives two different answers. The return window applies first, and the warranty starts after it.
- Each number has exactly one source section. Do a manual search pass for duplicate numbers.

## Doc updates in the same phase

- `prd.md`: confirm handbook v2 and the catalog categories.
- `AGENTS.md`: update the policy docs table and the version to v2.
- `CONTEXT.md`: add Exchange, Replacement and Store credit as terms.
- `correction.md`: entry "Handbook v2, written in full", listing the source URLs and the v1 ids that were kept.
- `explanation.md`: a short note on why the handbook comes first.

## Tasks

- [ ] Write `company-overview.md` (CO-ABOUT, CO-CATEGORIES, CO-SCOPE)
- [ ] Rewrite `returns-and-refunds.md`
- [ ] Write `exchanges.md` (EXC-* and REP-REPLACEMENT)
- [ ] Rewrite `shipping-and-delivery.md`
- [ ] Rewrite `warranty.md` and extend `order-changes.md`
- [ ] Write `payments-and-pricing.md` and `promotions-and-gift-cards.md`
- [ ] Extend `support-escalation.md`, `privacy-and-pii.md`, `faq-general.md`
- [ ] Rewrite `SECTION_IDS.md` for v2 and run the conflict checks
- [ ] Update `prd.md`, `AGENTS.md`, `CONTEXT.md`, `correction.md`, `explanation.md`
