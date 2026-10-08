import { expect, type Page, test } from "@playwright/test";

// Long enough for a viewer to read each screen.
const beat = (page: Page, ms = 2500) => page.waitForTimeout(ms);

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await beat(page, 1200);
  await page.getByLabel(/email/i).pressSequentially(email, { delay: 40 });
  await page.getByLabel(/password/i).pressSequentially(password, { delay: 40 });
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Case desk" })).toBeVisible();
  await beat(page);
}

async function ask(page: Page, question: string) {
  await page.locator('textarea[name="question"]').pressSequentially(question, { delay: 30 });
  await page.getByRole("button", { name: "Ask" }).click();
}

test("FAQ with citations, refund proposal, lead approval, ticket", async ({ page }) => {
  await signIn(page, "specialist@northstar.example", "northstar-specialist");

  await ask(page, "How long does a customer have to return a pair of shoes?");
  await expect(page.getByText(/Cited:/).first()).toBeVisible({ timeout: 120_000 });
  await page.getByText(/Cited:/).first().scrollIntoViewIfNeeded();
  await beat(page, 5000);

  await page.locator('input[name="query"]').pressSequentially("mira.shah@northstar.example", { delay: 30 });
  await page.getByRole("button", { name: "Bind" }).click();
  await expect(page.getByText("Mira Shah")).toBeVisible();
  await beat(page);

  await ask(page, "Please refund order NS-1001.");
  await expect(page.getByText("Waiting for approval").first()).toBeVisible({ timeout: 120_000 });
  await page.getByText("Waiting for approval").first().scrollIntoViewIfNeeded();
  await beat(page, 5000);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("heading", { name: "Northstar" })).toBeVisible();

  await signIn(page, "lead@northstar.example", "northstar-lead");
  await expect(page.getByRole("heading", { name: "Waiting for approval" })).toBeVisible();
  await expect(page.getByText(/NS-1001/).first()).toBeVisible();
  await beat(page, 5000);

  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/^Ticket /).first()).toBeVisible({ timeout: 60_000 });
  await beat(page, 5000);
});
