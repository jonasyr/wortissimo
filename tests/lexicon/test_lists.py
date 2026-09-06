from wortissimo.lexicon.lists import (
    FreqTable, build_lexicon, load_blocklist,
)

WORDS = {"haus", "dank", "gesetz", "raten", "ruppig", "alk", "ska", "nde", "xy"}

# Stand-in for Hunspell: any container answering "is this a real word?".
AUTHORITY = {"haus", "dank", "gesetz", "raten", "ruppig"}


def lex(blocklist=frozenset(), words=None, authority=None):
    return build_lexicon(words if words is not None else WORDS,
                         blocklist=blocklist,
                         authority=AUTHORITY if authority is None else authority)


def test_acceptance_is_generous():
    # Fragments the authority rejects stay acceptable: wrongly rejecting a
    # word the player knows is the worst failure mode in this genre.
    assert "alk" in lex().acceptance
    assert "nde" in lex().acceptance


def test_acceptance_drops_words_below_min_length():
    assert "xy" not in lex().acceptance


def test_solutions_drop_words_the_authority_rejects():
    solutions = lex().solutions
    assert "alk" not in solutions
    assert "ska" not in solutions
    assert "nde" not in solutions


def test_solutions_keep_real_words():
    solutions = lex().solutions
    for word in ("haus", "dank", "gesetz", "raten", "ruppig"):
        assert word in solutions


def test_solutions_never_include_a_non_accepted_word():
    # The authority alone is not enough; the word must also come from the
    # dictionary we accept from.
    assert "unbekannt" not in lex(authority={"unbekannt"}).solutions


def test_blocklist_removes_from_both_lists():
    result = lex(blocklist=frozenset({"haus"}))
    assert "haus" not in result.acceptance
    assert "haus" not in result.solutions


def test_solution_membership_is_memoized():
    solutions = lex().solutions
    assert "haus" in solutions
    assert solutions._cache["haus"] is True


def test_frequencies_are_available_for_difficulty_tuning():
    result = lex()
    assert result.freq["haus"] > result.freq["ruppig"]


def test_freq_table_computes_lazily_and_caches():
    table = FreqTable()
    assert table["haus"] > 0
    assert "haus" in table
    # .get must also populate, so callers cannot silently read 0.0
    assert table.get("gesetz") > 0


def test_blocklist_file_parsing(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("# comment\nberlin\n\n  hamburg  \n", encoding="utf-8")
    assert load_blocklist(p) == frozenset({"berlin", "hamburg"})


def test_acceptance_cache_is_stale_when_missing(tmp_path):
    from wortissimo.lexicon.lists import acceptance_cache_is_stale
    assert acceptance_cache_is_stale(tmp_path / "nope.bin", tmp_path / "b.txt")


def test_acceptance_cache_is_stale_when_the_blocklist_is_newer(tmp_path):
    import os, time
    from wortissimo.lexicon.lists import acceptance_cache_is_stale
    cache = tmp_path / "acc.bin"
    block = tmp_path / "b.txt"
    cache.write_bytes(b"x")
    time.sleep(0.01)
    block.write_text("berlin\n", encoding="utf-8")
    os.utime(block, (time.time() + 10, time.time() + 10))
    # A blocklist edit must invalidate the cache, or the edit silently
    # does nothing at all.
    assert acceptance_cache_is_stale(cache, block)


def test_acceptance_cache_is_fresh_when_older_blocklist(tmp_path):
    import os, time
    from wortissimo.lexicon.lists import acceptance_cache_is_stale
    block = tmp_path / "b.txt"
    cache = tmp_path / "acc.bin"
    block.write_text("berlin\n", encoding="utf-8")
    cache.write_bytes(b"x")
    os.utime(cache, (time.time() + 10, time.time() + 10))
    assert not acceptance_cache_is_stale(cache, block)
