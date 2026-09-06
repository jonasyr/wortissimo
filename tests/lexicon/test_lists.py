from wortissimo.lexicon.lists import build_lexicon, load_blocklist

# Real zipf values (wordfreq 3.1.1, German). Floor is 2.5.
#   haus 5.41  dank 5.32  gesetz 4.91  raten 4.29  ruppig 2.79
#   nde 2.44   aeh 1.95
# Proper nouns like 'ilm' (3.09) clear any usable floor and are handled by
# the blocklist, not by frequency.
WORDS = {"haus", "dank", "gesetz", "raten", "ruppig", "nde", "aeh", "xy"}


def test_acceptance_is_generous():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    # Low-frequency real-ish forms stay acceptable: rejecting a word the
    # player actually knows is the worst failure mode in this genre.
    assert "nde" in lex.acceptance
    assert "aeh" in lex.acceptance


def test_acceptance_drops_words_below_min_length():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert "xy" not in lex.acceptance


def test_solutions_drop_low_frequency_junk():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert "nde" not in lex.solutions
    assert "aeh" not in lex.solutions


def test_solutions_keep_real_words():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert {"haus", "dank", "gesetz", "raten", "ruppig"} <= lex.solutions


def test_solutions_are_a_subset_of_acceptance():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert lex.solutions <= lex.acceptance


def test_blocklist_removes_from_both_lists():
    lex = build_lexicon(WORDS, blocklist=frozenset({"haus"}))
    assert "haus" not in lex.solutions
    assert "haus" not in lex.acceptance


def test_frequencies_are_exposed_for_solutions():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert lex.freq["haus"] > lex.freq["raten"]


def test_blocklist_file_parsing(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("# comment\nberlin\n\n  hamburg  \n", encoding="utf-8")
    assert load_blocklist(p) == frozenset({"berlin", "hamburg"})


def test_short_words_need_a_much_higher_frequency():
    # 'art' 5.51 is a real word; 'alk' 3.28 and 'ska' 3.15 are fragments
    # that a single global floor would wrongly admit as solutions.
    words = {"art", "ort", "alk", "ska", "che", "tel"}
    lex = build_lexicon(words, blocklist=frozenset())
    assert {"art", "ort"} <= lex.solutions
    assert not ({"alk", "ska", "che"} & lex.solutions)


def test_short_junk_is_still_accepted_when_typed():
    # Cleanliness applies to what we REVEAL, never to what we accept.
    lex = build_lexicon({"alk", "ska"}, blocklist=frozenset())
    assert {"alk", "ska"} <= lex.acceptance


def test_long_words_keep_the_base_floor():
    from wortissimo.lexicon.lists import solution_floor
    assert solution_floor("ausbaden") == 2.5
    assert solution_floor("art") == 4.5
