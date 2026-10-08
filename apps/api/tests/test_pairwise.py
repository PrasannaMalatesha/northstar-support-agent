import random

from evals.pairwise import picks_from, pairwise_block, prefer


def test_identical_replies_tie_and_a_flipped_win_maps_back_to_v1():
    assert prefer("q", "same", "same", lambda *_: 1, random.Random(0)) == "tie"

    class _Flip:
        def random(self) -> float:
            return 0.0

    def grade(question: str, left: str, right: str) -> int:
        assert question == "q"
        assert left == "desk" and right == "handbook"
        return 1

    assert prefer("q", "handbook", "desk", grade, _Flip()) == "v1"


def test_a_recorded_block_lists_each_pick_once():
    text = pairwise_block({"exception": "v1", "holiday-window": "tie"})
    assert picks_from("# record\n\n" + text) == {"exception": "v1", "holiday-window": "tie"}
