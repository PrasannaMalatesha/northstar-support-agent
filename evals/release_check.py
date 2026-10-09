"""CI on a PR into uat: the release bar's results file must pass, for the code being promoted.

    python evals/release_check.py <head commit>

Standard library only, so CI runs it with no install and no keys.

The file names the commit whose code the release run measured. Committing the file makes a new commit,
so the head may differ from that commit by results files and nothing else. Any other change after the
run means the file is stale.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

RESULTS = "results/release_bar.json"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def problems(head: str) -> list[str]:
    """Why the head may not be promoted. Empty means it may."""
    shown = _git("show", f"{head}:{RESULTS}")
    if shown.returncode != 0:
        return [f"{RESULTS} is missing at {head}. Run `uv run python -m evals.experiments release` and commit the file."]
    try:
        bar = json.loads(shown.stdout)
    except json.JSONDecodeError:
        return [f"{RESULTS} is not valid JSON."]
    measured = str(bar.get("commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", measured) or _git("merge-base", "--is-ancestor", measured, head).returncode != 0:
        return [f"{RESULTS} names {measured or 'no commit'}, which is not in the history of {head}. Run the release bar again."]
    changed = _git("diff", "--name-only", measured, head).stdout.split()
    code = [path for path in changed if not path.startswith("results/")]
    if code:
        return [f"{RESULTS} measured {measured}, and these changed since: {', '.join(code)}. Run the release bar again."]
    gates = bar.get("gates")
    if not isinstance(gates, dict) or not gates:
        return [f"{RESULTS} lists no gates."]
    return [f"gate failed: {gate}" for gate, passed in gates.items() if passed is not True]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python evals/release_check.py <head commit>", file=sys.stderr)
        return 2
    found = problems(args[0])
    for problem in found:
        print(problem, file=sys.stderr)
    if not found:
        print(f"{RESULTS} passed for {args[0]}.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
