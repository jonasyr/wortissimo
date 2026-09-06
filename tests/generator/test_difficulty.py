from wortissimo.generator.difficulty import (
    Difficulty, classify_difficulty, metrics,
)
from wortissimo.generator.solve import Category, Solution


def sols(n_total, n_long=0, n_cross=0, n_trivial=0):
    """Build a solution list with the requested shape.

    'Trivial' means OBVIOUS_COMPONENT *and* high frequency, so the trivial
    entries are taken from the end while cross-boundary ones are taken from
    the start. Overlapping them would make n_trivial silently ineffective.
    """
    out = []
    for i in range(n_total):
        long_enough = i < n_long
        word = ("l" * 7 + str(i)) if long_enough else f"w{i:02d}"
        category = (Category.CROSS_BOUNDARY if i < n_cross
                    else Category.OBVIOUS_COMPONENT)
        freq = 5.5 if i >= n_total - n_trivial else 4.0
        out.append(Solution(word=word, category=category, freq=freq))
    return out


def test_leicht_word_is_classified_leicht():
    assert classify_difficulty("a" * 18, sols(12, 3, 1, 2)) is Difficulty.LEICHT


def test_brutal_word_is_classified_brutal():
    assert classify_difficulty("a" * 33, sols(25, 8, 10, 4)) is Difficulty.BRUTAL


def test_word_with_too_few_solutions_fits_no_bucket():
    assert classify_difficulty("a" * 18, sols(4)) is None


def test_word_that_is_too_short_fits_no_bucket():
    assert classify_difficulty("a" * 10, sols(12, 3, 1, 2)) is None


def test_word_with_too_few_cross_boundary_solutions_is_rejected():
    # Right length and count for Brutal, but no interesting finds.
    assert classify_difficulty("a" * 33, sols(25, 8, 0, 4)) is None


def test_too_many_trivial_solutions_is_rejected():
    # 20 of 25 solutions trivial = 80%, far over the Brutal ceiling.
    assert classify_difficulty("a" * 33, sols(25, 8, 10, 20)) is None


def test_schwer_band_is_classified_schwer():
    assert classify_difficulty("a" * 27, sols(20, 5, 6, 3)) is Difficulty.SCHWER


def test_mittel_band_is_classified_mittel():
    assert classify_difficulty("a" * 22, sols(15, 4, 4, 2)) is Difficulty.MITTEL


def test_metrics_reports_the_measured_shape():
    m = metrics("a" * 30, sols(40, 8, 15, 4))
    assert m["length"] == 30
    assert m["solution_count"] == 40
    assert m["long_count"] == 8
    assert m["cross_boundary_count"] == 15
    assert m["trivial_share"] == 4 / 40


def test_metrics_on_empty_solutions_does_not_divide_by_zero():
    m = metrics("a" * 20, [])
    assert m["trivial_share"] == 0.0


def test_buckets_do_not_overlap_in_length():
    from wortissimo.generator.difficulty import BUCKETS
    spans = sorted((b.min_len, b.max_len) for b in BUCKETS)
    for (_, prev_max), (next_min, _) in zip(spans, spans[1:]):
        assert prev_max < next_min
