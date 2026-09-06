from wortissimo.rules.validate import Rejection, validate_word

SOURCE = "straßenbahnhaltestelle"
ACCEPTANCE = {"bahn", "halte", "stelle", "haltestelle", "strasse",
              "strassenbahnhaltestelle", "enbahn", "raten"}


def v(word):
    return validate_word(word, SOURCE, ACCEPTANCE)


def test_accepts_a_plain_substring():
    assert v("Bahn").accepted is True
    assert v("Bahn").reason is None


def test_accepted_word_is_returned_normalized():
    assert v("BAHN").word == "bahn"


def test_rejects_too_short():
    assert v("ba").reason is Rejection.TOO_SHORT


def test_rejects_word_not_contiguous_in_source():
    # 'raten' is a real word in the acceptance list but its letters do not
    # appear contiguously in the source word.
    assert v("Raten").reason is Rejection.NOT_A_SUBSTRING


def test_rejects_word_not_in_dictionary():
    # 'senbah' IS a contiguous substring (stras|senbah|nhalte...) but is
    # not a German word.
    assert v("senbah").reason is Rejection.NOT_IN_DICTIONARY


def test_rejects_the_source_word_itself():
    assert v("Straßenbahnhaltestelle").reason is Rejection.IS_SOURCE_WORD


def test_rejects_malformed_input():
    assert v("bahn!").reason is Rejection.MALFORMED
    assert v("").reason is Rejection.MALFORMED


def test_source_word_is_normalized_before_matching():
    # Source given with capitals and ß; input given as ss.
    verdict = validate_word("Strasse", "Straßenbahn", {"strasse"})
    assert verdict.accepted is True


def test_check_order_short_beats_not_a_substring():
    # 'xy' is neither long enough nor a substring; length is reported first
    # because it is the more actionable message.
    assert v("xy").reason is Rejection.TOO_SHORT
