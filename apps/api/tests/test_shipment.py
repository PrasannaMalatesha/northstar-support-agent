"""The next step for a late or missing package follows SHIP-SLA, SHIP-DELAY, SHIP-LOST, and SHIP-DNR."""

from datetime import date

from northstar.actions import Order, Proposal, Reply, add_business_days, shipment


def _shipped(on: date) -> Order:
    return Order("NS-9", "shipped", on, None, "bags and accessories", "Canvas tote", "none", 4800, shipped_on=on)


def test_business_days_skip_the_weekend():
    assert add_business_days(date(2026, 10, 2), 1) == date(2026, 10, 5)  # Friday to Monday
    assert add_business_days(date(2026, 9, 23), 7) == date(2026, 10, 2)


def test_each_window_gives_its_own_next_step():
    shipped = date(2026, 9, 23)  # window ends 2 October, delayed after 6 October, lost on 7 October
    inside = shipment("never arrived", _shipped(shipped), date(2026, 10, 2))
    past_window = shipment("never arrived", _shipped(shipped), date(2026, 10, 5))
    lost = shipment("never arrived", _shipped(shipped), date(2026, 10, 7))
    assert isinstance(inside, Reply) and inside.citations == ("SHIP-SLA",)
    assert isinstance(past_window, Reply) and past_window.citations == ("SHIP-SLA", "SHIP-DELAY")
    assert isinstance(lost, Proposal) and lost.citations == ("SHIP-LOST",) and lost.amount_cents == 4800


def test_a_delayed_package_waits_and_is_not_called_lost():
    shipped = date(2026, 9, 7)  # Monday: window ends 16 September, delayed after 18 September, lost on 21 September
    delayed = shipment("late", _shipped(shipped), date(2026, 9, 19))
    assert isinstance(delayed, Reply)
    assert delayed.citations == ("SHIP-DELAY", "SHIP-LOST")
    assert "2026-09-21" in delayed.text


def test_no_carrier_or_tracking_number_is_invented():
    for today in (date(2026, 9, 25), date(2026, 10, 1), date(2026, 10, 20)):
        text = shipment("never arrived", _shipped(date(2026, 9, 23)), today).text.lower()
        assert "carrier" not in text and "tracking" not in text and "scan" not in text
