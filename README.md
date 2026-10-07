# Northstar Support Agent

Staff console for Northstar Goods. The specialist pastes the customer's words. A handbook answer cites a section or abstains. A refund waits for a lead before any ticket exists.

Malatesha decided the product, the handbook, the eval plan, and what good means. The console was implemented against those docs. Malatesha checked login, a cited handbook answer, a customer-scoped order, and a refund that waits for a person.

## Run

```
make db
make api
make web
make test
```

The API listens on `127.0.0.1:8000`. The console listens on `127.0.0.1:3000`. Postgres for the app is on port 5433. Staff accounts are seeded when the API starts. Their passwords stay in `packages/agent/northstar/identity/seed.py`.

Judges do not score the held-out set. `results/judge_calibration.md` still says they have not been run.
