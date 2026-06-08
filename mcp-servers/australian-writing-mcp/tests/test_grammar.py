from australian_writing.grammar import check_grammar


def _rules(result):
    return {i["rule"] for i in result["issues"]}


def _by_rule(result, rule):
    return [i for i in result["issues"] if i["rule"] == rule]


def test_clean_sentence_passes():
    assert check_grammar("The cat sat on the mat. It was warm.")["ok"]


def test_repeated_word():
    assert "repeated_word" in _rules(check_grammar("This is the the end."))


def test_modal_of():
    issue = _by_rule(check_grammar("I could of gone."), "modal_of")[0]
    assert issue["suggestion"] == "could have"


def test_spacing_and_punctuation():
    rules = _rules(check_grammar("Hello ,world.Next  one"))
    assert "space_before_punctuation" in rules
    assert "missing_space_after_punctuation" in rules
    assert "multiple_spaces" in rules


def test_sentence_capitalisation():
    assert "sentence_capitalisation" in _rules(check_grammar("the dog barked. it ran."))


def test_decimal_not_flagged():
    assert "missing_space_after_punctuation" not in _rules(check_grammar("Pi is about 3.14 today."))


# --- Indefinite article (ported from Harper) ---

def test_a_an_basic():
    suggestions = {i["suggestion"] for i in _by_rule(check_grammar("a elephant and an dog"), "a_an")}
    assert suggestions == {"an", "a"}


def test_a_before_consonant_sound_word():
    # "university" / "one" start with a consonant sound despite vowel letters.
    assert "a_an" not in _rules(check_grammar("She attends a university for a one-off event."))


def test_an_before_initialism():
    # "HTML"/"LLM" are spelled out, starting with a vowel sound -> "an".
    suggestions = [i["suggestion"] for i in _by_rule(check_grammar("a HTML page using a LLM"), "a_an")]
    assert suggestions == ["an", "an"]


def test_a_before_acronym():
    # "NASA"/"REST" are read as words starting with a consonant sound -> "a".
    assert "a_an" not in _rules(check_grammar("a NASA mission with a REST API"))


def test_an_herb_flagged_in_australian():
    # Australian English pronounces the "h" in herb, so "an herb" is wrong.
    assert _by_rule(check_grammar("an herb garden"), "a_an")[0]["suggestion"] == "a"


def test_either_sound_not_flagged():
    # "SQL" can be "an SQL" or "a SQL"; neither is flagged.
    assert "a_an" not in _rules(check_grammar("an SQL query and a SQL table"))


# --- Phrase corrections (ported from Harper) ---

def test_phrase_one_to_one():
    issue = _by_rule(check_grammar("And now, without further adieu."), "phrase")[0]
    assert issue["suggestion"] == "further ado"


def test_phrase_eggcorn_payed():
    assert _by_rule(check_grammar("He payed the bill."), "phrase")[0]["suggestion"] == "paid"


def test_phrase_many_to_many_alternatives():
    issue = _by_rule(check_grammar("This is a whole entire thing."), "phrase")[0]
    assert issue["suggestion"] == "a whole"  # "a whole entire" -> "a whole" / "an entire"


def test_phrase_preserves_case():
    issue = _by_rule(check_grammar("Payed in full."), "phrase")[0]
    assert issue["suggestion"] == "Paid"


def test_phrase_word_boundary():
    # "stdin" maps to "standard input"; must not fire inside a longer token.
    assert "phrase" not in _rules(check_grammar("The stdinx variable is unrelated."))
