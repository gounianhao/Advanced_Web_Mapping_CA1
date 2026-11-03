"""
Fairness score: how evenly the travel is shared between the friends.

    score = 100 x (1 - standard deviation / mean distance)

If everyone travels the same distance the standard deviation is 0 and the
score is 100. The more the distances differ, the lower the score. It is kept
between 0 and 100. The same formula is used in SQL to rank venues (see
spatial.rank_by_fairness), so a venue and a meeting point can be compared.
"""

from statistics import fmean, pstdev

FAIR_FROM = 75  # 75-100 is "Fair"
OK_FROM = 50    # 50-75 is "OK", below 50 is "Unfair"


def fairness_score(distances):
    """Return the 0-100 score for a list of distances in metres, or None if the list is empty."""
    distances = [float(d) for d in distances]
    if not distances:
        return None
    mean = fmean(distances)
    if mean == 0:
        return 100.0  # everyone is already at the same spot
    score = 100 * (1 - pstdev(distances) / mean)
    return round(min(100.0, max(0.0, score)), 1)


def fairness_label(score):
    """Turn a score into a word for the user interface."""
    if score is None:
        return None
    if score >= FAIR_FROM:
        return "Fair"
    if score >= OK_FROM:
        return "OK"
    return "Unfair"
