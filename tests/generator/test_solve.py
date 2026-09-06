from wortissimo.generator.solve import Category, find_solutions
from wortissimo.lexicon.lists import Lexicon


def make_lexicon(solutions: set[str], freqs: dict[str, float] | None = None):
    freqs = freqs or {w: 5.0 for w in solutions}
    return Lexicon(acceptance=frozenset(solutions),
                   solutions=frozenset(solutions), freq=freqs)


def words(result):
    return {s.word for s in result}


def category_of(result, word):
    return next(s.category for s in result if s.word == word)


def test_finds_a_substring_that_is_a_known_word():
    lex = make_lexicon({"bahn", "halte"})
    assert words(find_solutions("strassenbahnhalte", lex, ())) == {"bahn", "halte"}


def test_ignores_substrings_that_are_not_words():
    lex = make_lexicon({"bahn"})
    assert words(find_solutions("strassenbahn", lex, ())) == {"bahn"}


def test_excludes_the_source_word_itself():
    lex = make_lexicon({"bahn", "strassenbahn"})
    assert "strassenbahn" not in words(find_solutions("strassenbahn", lex, ()))


def test_excludes_words_shorter_than_min_length():
    lex = make_lexicon({"ba", "bahn"})
    assert words(find_solutions("strassenbahn", lex, ())) == {"bahn"}


def test_classifies_a_word_inside_one_morpheme_as_obvious():
    # boundary at 8: 'strassen|bahn'. 'bahn' sits wholly in the 2nd part.
    lex = make_lexicon({"bahn"})
    result = find_solutions("strassenbahn", lex, (8,))
    assert category_of(result, "bahn") is Category.OBVIOUS_COMPONENT


def test_classifies_a_word_straddling_a_boundary_as_cross_boundary():
    # boundary at 8: 'strassen|bahn'. 'enba' spans offsets 6..10.
    lex = make_lexicon({"enba"})
    result = find_solutions("strassenbahn", lex, (8,))
    assert category_of(result, "enba") is Category.CROSS_BOUNDARY


def test_word_at_several_positions_appears_once_and_takes_best_category():
    # 'eis' occurs at 2..5 (straddling boundary 4) and again at 7..10.
    lex = make_lexicon({"eis"})
    result = find_solutions("abeisxxeis", lex, (4,))
    assert len([s for s in result if s.word == "eis"]) == 1
    assert category_of(result, "eis") is Category.CROSS_BOUNDARY


def test_carries_frequency_through():
    lex = make_lexicon({"bahn"}, {"bahn": 5.04})
    result = find_solutions("strassenbahn", lex, ())
    assert result[0].freq == 5.04


def test_result_is_sorted_and_deterministic():
    lex = make_lexicon({"bahn", "halte", "stelle"})
    a = find_solutions("bahnhaltestelle", lex, ())
    b = find_solutions("bahnhaltestelle", lex, ())
    assert a == b
    assert [s.word for s in a] == sorted(s.word for s in a)


def test_no_boundaries_means_everything_is_obvious():
    lex = make_lexicon({"bahn", "enba"})
    result = find_solutions("strassenbahn", lex, ())
    assert all(s.category is Category.OBVIOUS_COMPONENT for s in result)
