"""The CI check on a PR into uat, run against throwaway git repositories, and its CI wiring."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from evals.release_bar import GATES
from evals.release_check import RESULTS, problems

ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "evals/release_check.py"


def _git(repo: Path, *args: str) -> str:
    quiet = ["-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    return subprocess.run(["git", *quiet, *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _bar(commit: str, failing: tuple[str, ...] = ()) -> str:
    return json.dumps({"commit": commit, "gates": {gate: gate not in failing for gate in GATES}})


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> Path:
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_head_passes_when_only_results_changed_after_the_measured_commit(repo):
    measured = _commit(repo, {"app.py": "one\n"}, "Code.")
    head = _commit(repo, {RESULTS: _bar(measured), "results/langsmith_test.md": "report\n"}, "Release bar.")
    assert problems(head) == []


def test_a_missing_file_fails(repo):
    head = _commit(repo, {"app.py": "one\n"}, "Code.")
    assert "missing" in problems(head)[0]


def test_a_file_from_before_a_code_change_is_stale(repo):
    measured = _commit(repo, {"app.py": "one\n"}, "Code.")
    _commit(repo, {RESULTS: _bar(measured)}, "Release bar.")
    head = _commit(repo, {"app.py": "two\n"}, "More code.")
    assert problems(head) == [f"{RESULTS} measured {measured}, and these changed since: app.py. Run the release bar again."]


def test_a_file_naming_another_commit_fails(repo):
    _commit(repo, {"app.py": "one\n"}, "Code.")
    _git(repo, "checkout", "-q", "-b", "elsewhere")
    elsewhere = _commit(repo, {"other.py": "x\n"}, "Elsewhere.")
    _git(repo, "checkout", "-q", "-")
    head = _commit(repo, {RESULTS: _bar(elsewhere)}, "Release bar from another branch.")
    assert "not in the history" in problems(head)[0]
    head = _commit(repo, {RESULTS: _bar("HEAD")}, "A name, not a commit.")
    assert "not in the history" in problems(head)[0]


def test_a_failing_gate_or_no_gates_fails(repo):
    measured = _commit(repo, {"app.py": "one\n"}, "Code.")
    head = _commit(repo, {RESULTS: _bar(measured, failing=("latency", "spanish latency"))}, "Release bar.")
    assert problems(head) == ["gate failed: latency", "gate failed: spanish latency"]
    head = _commit(repo, {RESULTS: json.dumps({"commit": measured, "gates": {}})}, "Empty.")
    assert problems(head) == [f"{RESULTS} lists no gates."]


def test_the_command_exits_nonzero_unless_the_file_passes(repo):
    measured = _commit(repo, {"app.py": "one\n"}, "Code.")
    missing = subprocess.run([sys.executable, str(CHECK), measured], cwd=repo, capture_output=True, text=True)
    assert missing.returncode == 1 and "missing" in missing.stderr
    head = _commit(repo, {RESULTS: _bar(measured)}, "Release bar.")
    passed = subprocess.run([sys.executable, str(CHECK), head], cwd=repo, capture_output=True, text=True)
    assert passed.returncode == 0, passed.stderr


def test_ci_checks_the_file_only_on_pull_requests_into_uat():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["release-bar"]
    assert job["if"] == "github.event_name == 'pull_request' && github.base_ref == 'uat'"
    checkout = job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {"ref": "${{ github.event.pull_request.head.sha }}", "fetch-depth": 0}
    assert job["steps"][1]["run"] == 'python3 evals/release_check.py "${{ github.event.pull_request.head.sha }}"'
    # No keys: the job reads no secret and installs nothing.
    assert "secrets." not in json.dumps(job)
    # The jobs on a PR into dev are as they were.
    assert "if" not in workflow["jobs"]["test"] and "if" not in workflow["jobs"]["web"]
    assert "pull_request" in workflow[True]  # PyYAML reads the key `on` as True
