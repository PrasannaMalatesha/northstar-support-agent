// The staff API token lasts 15 minutes. It is renewed with the refresh token shortly before it ends.
// Server code only.
//
// The API rotates refresh tokens: each one works once. In one request, the middleware and the page both
// read the same session cookie, so they must share one renewal. Middleware runs on the Node.js runtime
// (middleware.ts), so both reach this process-wide map.

const apiUrl = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";
const RENEW_BEFORE_SECONDS = 60;
const KEEP_MS = 60_000;

export type StaffTokens = { accessToken: string; refreshToken: string };

type Renewal = { at: number; tokens: Promise<StaffTokens | null> };
const store = globalThis as typeof globalThis & { northstarRenewals?: Map<string, Renewal> };
const renewals = (store.northstarRenewals ??= new Map<string, Renewal>());

// True when the access token ends within a minute, or cannot be read.
export function endsSoon(accessToken: string): boolean {
  try {
    const part = accessToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const { exp } = JSON.parse(atob(part)) as { exp?: number };
    return typeof exp !== "number" || exp - Date.now() / 1000 < RENEW_BEFORE_SECONDS;
  } catch {
    return true;
  }
}

// New tokens for this refresh token, or null when the API refuses it. One API call per refresh token.
export function renew(refreshToken: string): Promise<StaffTokens | null> {
  const now = Date.now();
  for (const [key, renewal] of renewals) {
    if (now - renewal.at > KEEP_MS) {
      renewals.delete(key);
    }
  }
  const known = renewals.get(refreshToken);
  if (known) {
    return known.tokens;
  }
  const tokens = fetch(`${apiUrl}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  })
    .then(async (response) => {
      if (!response.ok) {
        return null;
      }
      const body = (await response.json()) as { access_token: string; refresh_token: string };
      return { accessToken: body.access_token, refreshToken: body.refresh_token };
    })
    .catch(() => null)
    .then((renewed) => {
      // A refused or failed renewal is not kept, so a later request can try again.
      if (!renewed) {
        renewals.delete(refreshToken);
      }
      return renewed;
    });
  renewals.set(refreshToken, { at: now, tokens });
  return tokens;
}
