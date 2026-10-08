"""The LangSmith online judge prompt, checked without a network call."""

from northstar.handbook import registry_ids
from northstar.online import GROUNDED_KEY, groundedness_prompt


def test_the_judge_prompt_carries_the_whole_handbook_and_the_trace_fields():
    (role, system), (human_role, human) = groundedness_prompt()
    assert (role, human_role) == ("system", "human")
    assert all(f"[{section_id}]" in system for section_id in registry_ids())
    assert GROUNDED_KEY in system
    for variable in ("{{question}}", "{{citations}}", "{{reply}}"):
        assert variable in human


def test_the_judge_prompt_holds_no_key():
    text = " ".join(part for message in groundedness_prompt() for part in message)
    assert "sk-or-" not in text and "sk-" not in text
