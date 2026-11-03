"""The fairness score on its own (no database needed)."""

from meetups.services.fairness import fairness_label, fairness_score


def test_equal_distances_are_perfectly_fair():
    assert fairness_score([1200, 1200, 1200]) == 100.0


def test_everyone_at_the_same_spot_scores_100_without_dividing_by_zero():
    assert fairness_score([0, 0, 0]) == 100.0


def test_uneven_distances_score_lower():
    # mean 200, standard deviation 100 -> 100 x (1 - 100/200) = 50
    assert fairness_score([100, 300]) == 50.0


def test_score_never_goes_below_zero():
    assert fairness_score([0, 0, 0, 1000]) == 0.0


def test_no_distances_gives_no_score():
    assert fairness_score([]) is None


def test_labels():
    assert fairness_label(92) == "Fair"
    assert fairness_label(75) == "Fair"
    assert fairness_label(60) == "OK"
    assert fairness_label(20) == "Unfair"
    assert fairness_label(None) is None
