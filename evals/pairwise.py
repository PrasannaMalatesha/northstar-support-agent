"""Which reply a judge prefers, v0 or v1.

https://docs.langchain.com/langsmith/evaluate-pairwise
`evaluate_comparative` compares two named experiments. Those experiments are
not uploaded. This is that judge, with the order randomized, on the replies.
"""

from __future__ import annotations

import os
import random
from typing import Annotated, Callable, TypedDict

from evals.judge import JUDGE_MODEL_DEFAULT, OPENROUTER_BASE

GradeFn = Callable[[str, str, str], int]


class _Pick(TypedDict):
    reasoning: Annotated[str, ..., "Which reply is more accurate, and why."]
    preference: Annotated[int, ..., "0 for a tie, 1 if reply A is better, 2 if reply B is better."]


def prefer(question: str, v0: str, v1: str, grade: GradeFn, rng: random.Random) -> str:
    if v0.strip() == v1.strip():
        return "tie"
    # Same flag as evaluate_comparative(randomize_order=True).
    flip = rng.random() < 0.5
    left, right = (v1, v0) if flip else (v0, v1)
    choice = grade(question, left, right)
    if choice == 1:
        return "v1" if flip else "v0"
    if choice == 2:
        return "v0" if flip else "v1"
    return "tie"


def pairwise_block(picks: dict[str, str]) -> str:
    lines = [
        "## LLM pairwise",
        "",
        "The judge compared the two replies. The order was randomized.",
        "Identical replies are a tie and were not sent to the model.",
        "",
    ]
    for kind in ("v1", "v0", "tie"):
        ids = [case_id for case_id, pick in picks.items() if pick == kind]
        lines.append(f"{kind}: {', '.join(ids) if ids else 'none'}.")
    lines.append("")
    return "\n".join(lines)


def picks_from(text: str) -> dict[str, str]:
    section = text.split("## LLM pairwise", 1)[1]
    picks: dict[str, str] = {}
    for kind in ("v1", "v0", "tie"):
        for line in section.splitlines():
            if not line.startswith(f"{kind}:"):
                continue
            rest = line.split(":", 1)[1].strip().rstrip(".")
            if rest and rest != "none":
                for case_id in rest.split(", "):
                    picks[case_id] = kind
    return picks


def live_grade(question: str, left: str, right: str) -> int:
    from langchain.chat_models import init_chat_model

    name = os.environ.get("JUDGE_MODEL") or JUDGE_MODEL_DEFAULT
    grader = init_chat_model(
        name,
        model_provider="openai",
        base_url=OPENROUTER_BASE,
        api_key=os.environ["OPENROUTER_API_KEY"],
        temperature=0,
    ).with_structured_output(_Pick, method="json_schema", strict=True)
    messages = [
        {
            "role": "system",
            "content": (
                "You compare two support replies to the same question. "
                "Prefer the reply that is more factually accurate. "
                "Ignore order and length. Reply 0 for a tie, 1 if A is better, 2 if B is better."
            ),
        },
        {
            "role": "user",
            "content": f"QUESTION: {question}\n\nREPLY A: {left}\n\nREPLY B: {right}",
        },
    ]
    choice = int(grader.invoke(messages)["preference"])
    return choice if choice in (0, 1, 2) else 0


def _record() -> None:
    """Write results/v0_v1.md. Not collected by pytest."""
    import sys
    from datetime import datetime, timezone
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root), str(root / "apps/api"), str(root / "apps/api/tests")]

    from fastapi.testclient import TestClient
    from northstar.agent_model import _load_local_env
    from northstar.clock import SystemClock
    from northstar.handbook import answer
    from northstar.identity.postgres import PostgresIdentityStore
    from northstar.identity.seed import seed_staff
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from conftest import TEST_URL, _ensure_test_database
    from evals.labeled import CASES, comparison_text, score_naive
    from northstar_api.main import create_app
    from northstar_api.settings import Settings
    from test_labeled_set import _desk_passed

    _load_local_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("judge key is unset")

    class _Clock(SystemClock):
        def __init__(self) -> None:
            self.moment = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)

        def now(self):
            return self.moment

        def advance(self, **kwargs) -> None:
            from datetime import timedelta

            self.moment = self.moment + timedelta(**kwargs)

    _ensure_test_database()
    pool = ConnectionPool(TEST_URL, min_size=1, max_size=2, kwargs={"row_factory": dict_row}, open=True)
    clock = _Clock()
    app = create_app(
        settings=Settings(
            database_url=TEST_URL,
            token_secret="test-token-secret-at-least-32-characters",
        ),
        clock=clock,
        pool=pool,
    )
    PostgresIdentityStore(pool).truncate()
    seed_staff(PostgresIdentityStore(pool))
    texts: dict[str, str] = {}
    with TestClient(app) as client:
        naive_runs = [score_naive() for _ in range(3)]
        v0_runs = [{row["id"]: row["passed"] for row in run} for run in naive_runs]
        channels = {case["id"]: case["channel"] for case in CASES}
        v1_runs = []
        for _ in range(3):
            desk = _desk_passed(client, clock, texts)
            v1_runs.append(
                {
                    row["id"]: row["passed"] if channels[row["id"]] == "handbook" else desk[row["id"]]
                    for row in naive_runs[0]
                }
            )
    pool.close()

    rng = random.Random(0)
    picks: dict[str, str] = {}
    for case in CASES:
        if case["split"] != "test":
            continue
        v0 = answer(case["question"]).text
        v1 = v0 if case["channel"] == "handbook" else texts[case["id"]]

        def grade(question: str, left: str, right: str) -> int:
            try:
                return live_grade(question, left, right)
            except Exception:
                return live_grade(question, left, right)

        picks[case["id"]] = prefer(case["question"], v0, v1, grade, rng)
        print(case["id"], picks[case["id"]], flush=True)

    label = comparison_text(v0_runs, v1_runs, naive_runs[0])
    Path("results/v0_v1.md").write_text(label + "\n" + pairwise_block(picks))


if __name__ == "__main__":
    _record()
