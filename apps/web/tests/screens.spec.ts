import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

async function focused(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) {
      return "";
    }
    return el.getAttribute("name") || el.textContent?.trim() || "";
  });
}

async function tabTo(page: Page, name: string) {
  for (let i = 0; i < 40; i += 1) {
    if ((await focused(page)) === name) {
      return;
    }
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab did not reach ${name}. Focused: ${await focused(page)}`);
}

async function noViolations(page: Page) {
  const result = await new AxeBuilder({ page }).analyze();
  expect(result.violations, JSON.stringify(result.violations, null, 2)).toEqual([]);
}

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
  await noViolations(page);
  await tabTo(page, "email");
  await page.keyboard.type(email);
  await tabTo(page, "password");
  await page.keyboard.type(password);
  await tabTo(page, "Sign in");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Case desk" })).toBeVisible();
}

test("login, the case desk, and the waiting list pass axe and the keyboard", async ({ page }) => {
  await signIn(page, "specialist@northstar.example", "northstar-specialist");
  await noViolations(page);

  await tabTo(page, "query");
  await page.keyboard.type("mira.shah@northstar.example");
  await tabTo(page, "Bind");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Mira Shah")).toBeVisible();

  await tabTo(page, "question");
  await page.keyboard.type("Please refund order NS-1001.");
  await tabTo(page, "Ask");
  await page.keyboard.press("Enter");
  // A live refund turn calls the model. Under load it can pass the default 5 s, as the photo test allows for.
  await expect(page.getByText("Waiting for approval")).toBeVisible({ timeout: 30_000 });

  await tabTo(page, "Log out");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Northstar" })).toBeVisible();

  await signIn(page, "lead@northstar.example", "northstar-lead");
  await expect(page.getByRole("heading", { name: "Waiting for approval" })).toBeVisible();
  await noViolations(page);
  await tabTo(page, "Open case NS-1001");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Reading case/)).toBeVisible();
  await noViolations(page);
  await tabTo(page, "Back to my desk");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Waiting for approval" })).toBeVisible();
  await tabTo(page, "Approve");
  await page.keyboard.press("Enter");
  await expect(page.getByText("No proposal is waiting.")).toBeVisible();
});

test("a damaged-item photo is attached and described for the lead", async ({ page }) => {
  await signIn(page, "specialist@northstar.example", "northstar-specialist");
  // Start from a fresh case: close whatever the specialist left open.
  const resolve = page.getByRole("button", { name: "Resolve" });
  if (await resolve.isVisible()) {
    await page.getByLabel("Final text").fill("Closed.");
    await resolve.click();
  }
  await page.getByRole("button", { name: "New case" }).click();
  await page.getByLabel("Customer email or phone").fill("mira.shah@northstar.example");
  await page.getByRole("button", { name: "Bind" }).click();
  await expect(page.getByText("Mira Shah")).toBeVisible();

  await page.getByLabel("Handbook question").fill("The desk lamp on order NS-1011 arrived damaged.");
  await page
    .getByLabel("Photo of the item (optional)")
    .setInputFiles(path.resolve(process.cwd(), "../../evals/photos/lamp-cracked.png"));
  await page.getByRole("button", { name: "Ask" }).click();
  // With a model key the verdict is shown; without one (CI) the photo is noted as not described.
  // A live turn plus the vision call can take several seconds.
  await expect(page.getByText(/Photo: (visible damage|attached, but it could not be described)/).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("REF-DAMAGED").first()).toBeVisible();
  await noViolations(page);
});

test("a customer chat starts from an order and email, and a refund waits for a person", async ({ page }) => {
  await page.goto("/chat");
  await noViolations(page);
  await page.getByLabel("Order id").fill("NS-1006");
  await page.getByLabel("Email").fill("someone.else@example.com");
  await page.getByRole("button", { name: "Start chat" }).click();
  await expect(page.getByText("That order and email do not match.")).toBeVisible();

  await page.getByLabel("Order id").fill("NS-1006");
  await page.getByLabel("Email").fill("mira.shah@northstar.example");
  await page.getByRole("button", { name: "Start chat" }).click();
  await expect(page.getByLabel("Your message")).toBeVisible();
  await noViolations(page);

  await page.getByLabel("Your message").fill("Please refund order NS-1006.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Nothing is approved yet/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Amount/)).toHaveCount(0);
  await noViolations(page);

  // While the request waits for a person, another message is refused with a reason, not dropped.
  await page.getByLabel("Your message").fill("Any news on my refund?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Your request is with our team. You can write again once they reply.")).toBeVisible();

  await page.getByRole("button", { name: "End chat" }).click();
  await expect(page.getByRole("button", { name: "Start chat" })).toBeVisible();
});

test("an escalated chat reaches the escalations inbox, and the specialist's reply reaches the chat", async ({ page }) => {
  // Jon Hale, so this chat does not meet Mira's case from the test above.
  await page.goto("/chat");
  await page.getByLabel("Order id").fill("NS-1002");
  await page.getByLabel("Email").fill("jon.hale@northstar.example");
  await page.getByRole("button", { name: "Start chat" }).click();
  await page.getByLabel("Your message").fill("I will open a chargeback with my bank.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/same order id and email to read the reply/)).toBeVisible({ timeout: 30_000 });
  await noViolations(page);

  // The chat cookie lives on /chat, so the staff sign-in in the same browser does not touch it.
  await signIn(page, "specialist@northstar.example", "northstar-specialist");
  await expect(page.getByRole("heading", { name: "Escalations inbox" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Customer chat, Jon Hale/ })).toBeVisible();
  await noViolations(page);
  await tabTo(page, "Pick up");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Picked up by you.")).toBeVisible();
  await noViolations(page);
  await tabTo(page, "reply");
  await page.keyboard.type("Hi Jon, our payments team has your dispute. No refund is promised yet.");
  await tabTo(page, "Send reply");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Reply sent. The customer sees it in their chat.")).toBeVisible();
  await noViolations(page);

  await tabTo(page, "Log out");
  await page.keyboard.press("Enter");
  await signIn(page, "lead@northstar.example", "northstar-lead");
  await expect(page.getByText("Picked up by Avery Cole.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Pick up" })).toHaveCount(0);
  await noViolations(page);

  await page.goto("/chat");
  await expect(page.getByText("Avery, Northstar specialist:")).toBeVisible();
  await expect(page.getByText("Hi Jon, our payments team has your dispute. No refund is promised yet.")).toBeVisible();
  await noViolations(page);
});

test("three replies that did not help offer a person, and a customer turned away leaves a message for the inbox", async ({
  page,
}) => {
  // Jon Hale again: after the escalation above, his next message starts a new chat case.
  await page.goto("/chat");
  await page.getByLabel("Order id").fill("NS-1002");
  await page.getByLabel("Email").fill("jon.hale@northstar.example");
  await page.getByRole("button", { name: "Start chat" }).click();
  const person = page.getByRole("heading", { name: "Talk to a person" });
  const leaveMessage = page.getByRole("heading", { name: "Leave a message for a specialist" });
  for (const question of ["What is your favorite color?", "Tell me a joke.", "Who won the game last night?"]) {
    await expect(person).toHaveCount(0);
    await page.getByLabel("Your message", { exact: true }).fill(question);
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(question)).toBeVisible({ timeout: 30_000 });
  }
  // With live chat on, the follow-up is a person (issue #141). One button, inside the follow-up.
  await expect(person).toBeVisible();
  await expect(page.getByText("These replies have not helped. A specialist can join this chat.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Talk to a person" })).toHaveCount(1);
  await expect(leaveMessage).toHaveCount(0);
  await noViolations(page);

  // Nobody is available yet, so the line turns Jon away and the chat offers to leave a message.
  await tabTo(page, "Talk to a person");
  await page.keyboard.press("Enter");
  await expect(leaveMessage).toBeVisible();
  await expect(person).toHaveCount(0);
  await noViolations(page);

  await tabTo(page, "message");
  await page.keyboard.type("I would like a person to help me choose a gift.");
  await tabTo(page, "Leave message");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Your message is with our team. A specialist will reply in this chat.")).toBeVisible();
  await expect(page.getByText(/same order id and email to read the reply/)).toBeVisible();
  await expect(leaveMessage).toHaveCount(0);
  await noViolations(page);

  await signIn(page, "specialist@northstar.example", "northstar-specialist");
  const left = page.getByRole("article").filter({ hasText: "The customer left this message for a specialist." });
  await expect(left.getByText(/Asked: I would like a person to help me choose a gift\./)).toBeVisible();
  await noViolations(page);
  await left.getByRole("button", { name: "Pick up" }).click();
  await left.getByLabel("Reply to the customer").fill("Hi Jon, the canvas tote is a popular gift.");
  await left.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText("Reply sent. The customer sees it in their chat.")).toBeVisible();

  await page.goto("/chat");
  await expect(page.getByText("Hi Jon, the canvas tote is a popular gift.")).toBeVisible();
  await noViolations(page);
});

test("with no specialist available the customer may leave a message, and a waiting customer can leave the line", async ({
  page,
  browser,
}) => {
  const specialistContext = await browser.newContext();
  const specialist = await specialistContext.newPage();
  // Jon Hale: his last chat case was escalated above, so asking for a person starts a new one.
  await page.goto("/chat");
  await page.getByLabel("Order id").fill("NS-1002");
  await page.getByLabel("Email").fill("jon.hale@northstar.example");
  await page.getByRole("button", { name: "Start chat" }).click();
  await page.getByRole("button", { name: "Talk to a person" }).click();
  await expect(
    page.getByText("No specialist can join soon. Leave a message, and a specialist will reply in this chat."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Leave a message for a specialist" })).toBeVisible();
  await expect(page.getByText(/These replies have not helped/)).toHaveCount(0);
  await noViolations(page);

  // A specialist is available now: the customer joins the line and sees their place.
  await signIn(specialist, "specialist@northstar.example", "northstar-specialist");
  await tabTo(specialist, "Set Available");
  await specialist.keyboard.press("Enter");
  await expect(specialist.getByRole("button", { name: "Set Away" })).toBeVisible();
  await page.getByRole("button", { name: "Talk to a person" }).click();
  await expect(page.getByText("You are next in line. A specialist is about to join the chat.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Leave a message for a specialist" })).toHaveCount(0);
  const offer = specialist.getByRole("article").filter({ hasText: "Jon Hale asked to talk to a person." });
  await expect(offer).toBeVisible({ timeout: 10_000 });
  await noViolations(page);

  // Leaving the line takes the customer back to the agent and withdraws the offer.
  await tabTo(page, "Leave the line");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Talk to a person" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Leave the line" })).toHaveCount(0);
  await expect(page.getByText(/in line/)).toHaveCount(0);
  await noViolations(page);
  await expect(offer).toHaveCount(0, { timeout: 10_000 });

  await specialist.getByRole("button", { name: "Set Away" }).click();
  await expect(specialist.getByRole("button", { name: "Set Available" })).toBeVisible();
  await specialistContext.close();
});

test("a customer talks to a specialist in a live chat, and the specialist resolves the case", async ({ page, browser }) => {
  // Three browsers: the customer, the specialist, and a lead who reads the outcome.
  const customer = page;
  const specialistContext = await browser.newContext();
  const leadContext = await browser.newContext();
  const specialist = await specialistContext.newPage();
  const lead = await leadContext.newPage();

  // A specialist is available first: with nobody available, the customer is offered to leave a message.
  await signIn(specialist, "specialist@northstar.example", "northstar-specialist");
  await expect(specialist.getByRole("heading", { name: "Live chats" })).toBeVisible();
  await noViolations(specialist);
  await tabTo(specialist, "Set Available");
  await specialist.keyboard.press("Enter");
  await expect(specialist.getByRole("button", { name: "Set Away" })).toBeVisible();

  // Jon Hale: Mira's chat waits for a lead after the refund test above.
  await customer.goto("/chat");
  await customer.getByLabel("Order id").fill("NS-1002");
  await customer.getByLabel("Email").fill("jon.hale@northstar.example");
  await customer.getByRole("button", { name: "Start chat" }).click();
  await customer.getByRole("button", { name: "Talk to a person" }).click();
  await expect(customer.getByText("Waiting for a person.")).toBeVisible();
  await expect(customer.getByRole("button", { name: "Talk to a person" })).toHaveCount(0);
  await noViolations(customer);

  const offer = specialist.getByRole("article").filter({ hasText: "Jon Hale asked to talk to a person." });
  await expect(offer).toBeVisible({ timeout: 10_000 });
  await noViolations(specialist);
  await offer.getByRole("button", { name: "Accept" }).click();
  await expect(specialist.getByRole("heading", { name: "Live chat with Jon Hale" })).toBeVisible();
  await noViolations(specialist);
  await tabTo(specialist, "text");
  await specialist.keyboard.type("Hi Jon, this is Avery. How can I help?");
  await tabTo(specialist, "Send");
  await specialist.keyboard.press("Enter");
  await expect(specialist.getByText("Hi Jon, this is Avery. How can I help?")).toBeVisible();

  // The customer chat refreshes every 3 seconds while the live chat is open.
  await expect(customer.getByText("Avery joined the chat.")).toBeVisible({ timeout: 10_000 });
  await expect(customer.getByText("Hi Jon, this is Avery. How can I help?")).toBeVisible();
  await noViolations(customer);
  await customer.getByLabel("Your message", { exact: true }).fill("The strap on my canvas tote broke.");
  await customer.getByRole("button", { name: "Send" }).click();
  await expect(specialist.getByText("The strap on my canvas tote broke.")).toBeVisible({ timeout: 10_000 });

  const caseLine = await specialist.getByText(/^Case [0-9a-f-]{36}\./).textContent();
  const caseId = caseLine?.match(/[0-9a-f-]{36}/)?.[0];
  await specialist.getByRole("button", { name: "Resolve" }).click();
  await expect(specialist.getByText("Live chat resolved.")).toBeVisible();
  await noViolations(specialist);
  await expect(customer.getByText("This chat is closed. Write again to start a new one.")).toBeVisible({ timeout: 10_000 });
  await noViolations(customer);

  await signIn(lead, "lead@northstar.example", "northstar-lead");
  await lead.goto(`/desk?case=${caseId}`);
  await expect(lead.getByText(/Reading case/)).toBeVisible();
  await expect(lead.getByText("Resolved", { exact: true })).toBeVisible();
  await expect(lead.getByText("Hi Jon, this is Avery. How can I help?")).toBeVisible();
  await noViolations(lead);

  await specialistContext.close();
  await leadContext.close();
});

test("a specialist raises a refund in a live chat, and only a lead approves it", async ({ page, browser }) => {
  const customer = page;
  const specialistContext = await browser.newContext();
  const leadContext = await browser.newContext();
  const specialist = await specialistContext.newPage();
  const lead = await leadContext.newPage();

  // Available first: with nobody available, the line turns the customer away.
  await signIn(specialist, "specialist@northstar.example", "northstar-specialist");
  const setAvailable = specialist.getByRole("button", { name: "Set Available" });
  if (await setAvailable.count()) {
    await setAvailable.click();
  }
  await expect(specialist.getByRole("button", { name: "Set Away" })).toBeVisible();

  // Jon Hale again: his live chat above is resolved, so asking for a person starts a new case.
  await customer.goto("/chat");
  await customer.getByLabel("Order id").fill("NS-1002");
  await customer.getByLabel("Email").fill("jon.hale@northstar.example");
  await customer.getByRole("button", { name: "Start chat" }).click();
  await customer.getByRole("button", { name: "Talk to a person" }).click();

  const offer = specialist.getByRole("article").filter({ hasText: "Jon Hale asked to talk to a person." });
  await offer.getByRole("button", { name: "Accept" }).click();
  await expect(specialist.getByRole("heading", { name: "Live chat with Jon Hale" })).toBeVisible();
  await expect(specialist.getByText("Spanish", { exact: true })).toHaveCount(0);

  // The customer writes in Spanish. The specialist sees the label and replies in Spanish themselves.
  await expect(customer.getByText("Avery joined the chat.")).toBeVisible({ timeout: 10_000 });
  await customer.getByLabel("Your message", { exact: true }).fill("Hola, quiero un reembolso del pedido NS-1002.");
  await customer.getByRole("button", { name: "Send" }).click();
  await expect(specialist.getByText("Spanish", { exact: true })).toBeVisible({ timeout: 10_000 });
  await noViolations(specialist);
  await specialist.getByLabel("Your reply").fill("Hola Jon, soy Avery. Pido el reembolso a un líder.");
  await specialist.getByRole("button", { name: "Send", exact: true }).click();

  await tabTo(specialist, "request");
  await specialist.keyboard.type("Refund order NS-1002.");
  await tabTo(specialist, "Raise action");
  await specialist.keyboard.press("Enter");
  await expect(specialist.getByText(/^The customer sees: .*Nothing is approved yet\.$/)).toBeVisible();
  await expect(specialist.getByText("Refund order NS-1002.")).toBeVisible();
  await noViolations(specialist);

  // The customer sees that nothing is approved yet, the specialist's own words, and no amount or rule.
  await expect(customer.getByText(/Nothing is approved yet/)).toBeVisible({ timeout: 10_000 });
  await expect(customer.getByText("Hola Jon, soy Avery. Pido el reembolso a un líder.")).toBeVisible();
  await expect(customer.getByText(/Refund order|cents|REF-/)).toHaveCount(0);
  await noViolations(customer);

  // The live chat does not end while the proposal waits for a lead.
  await specialist.getByRole("button", { name: "Resolve" }).click();
  await expect(specialist.getByText(/proposal on this live chat is waiting for a lead/)).toBeVisible();
  await noViolations(specialist);

  await signIn(lead, "lead@northstar.example", "northstar-lead");
  const proposal = lead
    .locator("section")
    .filter({ has: lead.getByRole("heading", { name: "Waiting for approval" }) })
    .getByRole("article")
    .filter({ hasText: "NS-1002: " });
  // The rule sets the amount: a full refund inside the window, a deny after it.
  await expect(proposal.getByText(/^NS-1002: (approve_refund, 4800 cents|deny, 0 cents)/)).toBeVisible();
  await expect(proposal.getByText(/^Cited: REF-/)).toBeVisible();
  await noViolations(lead);
  await proposal.getByRole("button", { name: "Approve" }).click();
  await expect(lead.getByText(/^Ticket [0-9a-f-]{36}\.$/).first()).toBeVisible();

  await expect(customer.getByText(/Our team approved your request\. Reference/)).toBeVisible({ timeout: 10_000 });
  await expect(specialist.getByText(/^The customer sees: Our team approved your request/)).toBeVisible({ timeout: 10_000 });
  await specialist.getByRole("button", { name: "Resolve" }).click();
  await expect(specialist.getByText("Live chat resolved.")).toBeVisible();

  await specialistContext.close();
  await leadContext.close();
});

test("an escalation in the chat joins the line, and the specialist who accepts reads the handoff", async ({
  page,
  browser,
}) => {
  const customer = page;
  const specialistContext = await browser.newContext();
  const specialist = await specialistContext.newPage();

  // Available first: with nobody available, the escalation goes to the escalations inbox instead.
  await signIn(specialist, "specialist@northstar.example", "northstar-specialist");
  const setAvailable = specialist.getByRole("button", { name: "Set Available" });
  if (await setAvailable.count()) {
    await setAvailable.click();
  }
  await expect(specialist.getByRole("button", { name: "Set Away" })).toBeVisible();

  // Jon Hale again: his live chat above is resolved, so this message starts a new case.
  await customer.goto("/chat");
  await customer.getByLabel("Order id").fill("NS-1002");
  await customer.getByLabel("Email").fill("jon.hale@northstar.example");
  await customer.getByRole("button", { name: "Start chat" }).click();
  await customer.getByLabel("Your message", { exact: true }).fill("I will open a chargeback with my bank.");
  await customer.getByRole("button", { name: "Send" }).click();
  await expect(customer.getByText("You are next in line. A specialist is about to join the chat.")).toBeVisible({
    timeout: 30_000,
  });
  await expect(customer.getByText("A specialist will follow up with you about this.")).toBeVisible();
  await expect(customer.getByText(/Owner:|ESC-LEGAL/)).toHaveCount(0);
  await noViolations(customer);

  const offer = specialist.getByRole("article").filter({ hasText: "Jon Hale asked to talk to a person." });
  await offer.getByRole("button", { name: "Accept" }).click({ timeout: 10_000 });
  await expect(specialist.getByRole("heading", { name: "Live chat with Jon Hale" })).toBeVisible();
  await expect(specialist.getByRole("heading", { name: "Handoff" })).toBeVisible();
  await expect(specialist.getByText(/^Asked: I will open a chargeback with my bank\./)).toBeVisible();
  await expect(specialist.getByText(/Owner: legal/)).toBeVisible();
  await expect(
    specialist.getByRole("region", { name: "Conversation" }).getByText("I will open a chargeback with my bank."),
  ).toBeVisible();
  await noViolations(specialist);

  await expect(customer.getByText("Avery joined the chat.")).toBeVisible({ timeout: 10_000 });
  await specialist.getByRole("button", { name: "Resolve" }).click();
  await expect(specialist.getByText("Live chat resolved.")).toBeVisible();
  await specialist.getByRole("button", { name: "Set Away" }).click();
  await expect(specialist.getByRole("button", { name: "Set Available" })).toBeVisible();
  await specialistContext.close();
});

test("the lead sees the line and an alert when a customer waits for a specialist's reply", async ({ page, browser }) => {
  // Three browsers. The API flags a quiet specialist after 3 seconds here (playwright.config.ts).
  const customer = page;
  const specialistContext = await browser.newContext();
  const leadContext = await browser.newContext();
  const specialist = await specialistContext.newPage();
  const lead = await leadContext.newPage();

  await signIn(specialist, "specialist@northstar.example", "northstar-specialist");
  const setAvailable = specialist.getByRole("button", { name: "Set Available" });
  if (await setAvailable.count()) {
    await setAvailable.click();
  }
  await expect(specialist.getByRole("button", { name: "Set Away" })).toBeVisible();

  await signIn(lead, "lead@northstar.example", "northstar-lead");
  const line = lead.locator("section").filter({ has: lead.getByRole("heading", { name: "Line", exact: true }) });
  await expect(line.getByText("Specialists available: 1")).toBeVisible();
  await expect(line.getByText("Customers in line: 0")).toBeVisible();
  await expect(line.getByText("Longest wait: nobody is waiting")).toBeVisible();
  await expect(line.getByText(/^Average chat length: /)).toBeVisible();
  await expect(line.getByText("No alerts.")).toBeVisible();
  await noViolations(lead);

  // Jon Hale's live chat above is resolved, so asking for a person starts a new case.
  await customer.goto("/chat");
  await customer.getByLabel("Order id").fill("NS-1002");
  await customer.getByLabel("Email").fill("jon.hale@northstar.example");
  await customer.getByRole("button", { name: "Start chat" }).click();
  await customer.getByRole("button", { name: "Talk to a person" }).click();
  await expect(customer.getByText("Waiting for a person.")).toBeVisible();
  // The lead's desk refreshes every 3 seconds. An offer not yet accepted is still in the line.
  await expect(line.getByText("Customers in line: 1")).toBeVisible({ timeout: 10_000 });

  const offer = specialist.getByRole("article").filter({ hasText: "Jon Hale asked to talk to a person." });
  await offer.getByRole("button", { name: "Accept" }).click();
  await expect(specialist.getByRole("heading", { name: "Live chat with Jon Hale" })).toBeVisible();

  // Avery has not replied. The lead is alerted, and the live chat stays with Avery.
  const alert = line.getByText(/^Jon Hale has waited less than a minute for Avery's reply\. The chat stays with Avery\./);
  await expect(alert).toBeVisible({ timeout: 15_000 });
  await expect(line.getByText("Customers in line: 0")).toBeVisible();
  await noViolations(lead);
  await tabTo(lead, "Open Jon Hale's case");
  await lead.keyboard.press("Enter");
  await expect(lead.getByText(/Reading case/)).toBeVisible();
  await expect(lead.getByRole("heading", { name: "Line", exact: true })).toHaveCount(0);
  await tabTo(lead, "Back to my desk");
  await lead.keyboard.press("Enter");
  await expect(alert).toBeVisible();
  await expect(specialist.getByRole("heading", { name: "Live chat with Jon Hale" })).toBeVisible();

  // Avery replies, and the alert goes away.
  await specialist.getByLabel("Your reply").fill("Hi Jon, this is Avery. Sorry for the wait.");
  await specialist.getByRole("button", { name: "Send", exact: true }).click();
  await expect(line.getByText("No alerts.")).toBeVisible({ timeout: 10_000 });
  await noViolations(lead);
  await specialist.getByRole("button", { name: "Resolve" }).click();
  await expect(specialist.getByText("Live chat resolved.")).toBeVisible();

  await specialistContext.close();
  await leadContext.close();
});

test("a specialist declines a live chat offer, and the customer keeps waiting", async ({ page, browser }) => {
  const customer = page;
  const specialistContext = await browser.newContext();
  const specialist = await specialistContext.newPage();

  // Available first: with nobody available, the line turns the customer away.
  await signIn(specialist, "specialist@northstar.example", "northstar-specialist");
  const setAvailable = specialist.getByRole("button", { name: "Set Available" });
  if (await setAvailable.count()) {
    await setAvailable.click();
  }
  await expect(specialist.getByRole("button", { name: "Set Away" })).toBeVisible();

  // Jon Hale's live chat above is resolved, so asking for a person starts a new case.
  await customer.goto("/chat");
  await customer.getByLabel("Order id").fill("NS-1002");
  await customer.getByLabel("Email").fill("jon.hale@northstar.example");
  await customer.getByRole("button", { name: "Start chat" }).click();
  await customer.getByRole("button", { name: "Talk to a person" }).click();
  await expect(customer.getByText("Waiting for a person.")).toBeVisible();

  const offer = specialist.getByRole("article").filter({ hasText: "Jon Hale asked to talk to a person." });
  await expect(offer).toBeVisible();
  await expect(offer.getByRole("button", { name: "Decline" })).toBeVisible();
  await noViolations(specialist);
  await offer.getByRole("button", { name: "Decline" }).click();
  await expect(specialist.getByText("Offer declined. It goes to the next specialist.")).toBeVisible();
  await expect(offer).toHaveCount(0);
  await noViolations(specialist);

  // Avery is not offered it again, and nobody else is available: the customer waits in the line.
  await customer.reload();
  await expect(customer.getByText("Waiting for a person.")).toBeVisible();
  await expect(customer.getByText(/^You are number 1 in line\./)).toBeVisible();
  await expect(specialist.getByText("No live chat is offered to you.")).toBeVisible();

  await specialistContext.close();
});
