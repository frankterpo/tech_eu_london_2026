from agent.scheduler import frequencies_for_period


def test_monthly_period_fans_out_to_all_required_cadences():
    assert frequencies_for_period("monthly") == [
        "weekly",
        "monthly",
        "quarterly",
        "annual",
    ]


def test_non_monthly_period_uses_single_cadence():
    assert frequencies_for_period("weekly") == ["weekly"]
    assert frequencies_for_period("quarterly") == ["quarterly"]
    assert frequencies_for_period("annual") == ["annual"]
    assert frequencies_for_period("unknown") == []
