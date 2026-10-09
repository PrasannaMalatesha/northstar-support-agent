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
  await expect(page.getByText("Waiting for approval")).toBeVisible();

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
