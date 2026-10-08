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
