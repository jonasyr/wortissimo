from wortissimo.rules.scoring import score_round

SOLUTIONS = ["bahn", "halte", "stelle", "haltestelle", "strasse"]


def by_player(result):
    return {s.player: s for s in result.scores}


def test_shared_word_scores_one_each():
    result = score_round({"jw": ["bahn"], "gf": ["bahn"]}, SOLUTIONS)
    assert by_player(result)["jw"].points == 1
    assert by_player(result)["gf"].points == 1
    assert result.shared_words == ("bahn",)


def test_unique_word_scores_two():
    result = score_round({"jw": ["bahn"], "gf": ["halte"]}, SOLUTIONS)
    assert by_player(result)["jw"].points == 2
    assert by_player(result)["gf"].points == 2
    assert result.shared_words == ()


def test_unique_words_are_reported_per_player():
    result = score_round({"jw": ["bahn", "halte"], "gf": ["halte"]}, SOLUTIONS)
    assert by_player(result)["jw"].unique_words == ("bahn",)
    assert by_player(result)["gf"].unique_words == ()


def test_duplicate_submission_scores_once():
    result = score_round({"jw": ["bahn", "bahn"], "gf": []}, SOLUTIONS)
    assert by_player(result)["jw"].points == 2
    assert by_player(result)["jw"].words == ("bahn",)


def test_missed_words_are_solutions_nobody_found():
    result = score_round({"jw": ["bahn"], "gf": ["halte"]}, SOLUTIONS)
    assert result.missed_words == ("haltestelle", "stelle", "strasse")


def test_empty_round_scores_zero_and_misses_everything():
    result = score_round({"jw": [], "gf": []}, SOLUTIONS)
    assert by_player(result)["jw"].points == 0
    assert len(result.missed_words) == len(SOLUTIONS)


def test_output_ordering_is_deterministic():
    a = score_round({"jw": ["stelle", "bahn"], "gf": ["bahn"]}, SOLUTIONS)
    b = score_round({"jw": ["bahn", "stelle"], "gf": ["bahn"]}, SOLUTIONS)
    assert a == b


def test_solo_player_gets_two_points_per_word():
    result = score_round({"jw": ["bahn"]}, SOLUTIONS)
    assert by_player(result)["jw"].points == 2
