"""Path score from the complex-agent guide.

https://docs.langchain.com/langsmith/evaluate-complex-agent
Extra steps do not change the subsequence score. extra_step_count counts them.
"""

from __future__ import annotations


def trajectory_subsequence(outputs: dict, reference_outputs: dict) -> float | bool:
    """Check how many of the desired steps the agent took."""
    if len(reference_outputs["trajectory"]) > len(outputs["trajectory"]):
        return False

    i = j = 0
    while i < len(reference_outputs["trajectory"]) and j < len(outputs["trajectory"]):
        if reference_outputs["trajectory"][i] == outputs["trajectory"][j]:
            i += 1
        j += 1

    return i / len(reference_outputs["trajectory"])


def extra_step_count(outputs: dict, reference_outputs: dict) -> int:
    actual = outputs["trajectory"]
    reference = reference_outputs["trajectory"]
    matched = index = 0
    while matched < len(reference) and index < len(actual):
        if reference[matched] == actual[index]:
            matched += 1
        index += 1
    return len(actual) - matched
