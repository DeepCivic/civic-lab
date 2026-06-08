from australian_writing.spelling import check_spelling


def _words(result):
    return {i["word"]: i for i in result["issues"]}


def test_australian_spelling_passes():
    result = check_spelling("The colour of the harbour at the centre of town.")
    assert result["ok"], result["issues"]


def test_flags_american_spelling_as_americanism():
    result = check_spelling("The color of the harbor.")
    issues = _words(result)
    assert issues["color"]["category"] == "americanism"
    assert issues["color"]["suggestions"] == ["colour"]
    assert issues["harbor"]["suggestions"] == ["harbour"]


def test_ize_suffix_rule():
    result = check_spelling("We must organize and analyze the data.")
    issues = _words(result)
    assert issues["organize"]["suggestions"] == ["organise"]
    assert issues["analyze"]["suggestions"] == ["analyse"]


def test_flags_genuine_misspelling():
    result = check_spelling("I recieve mail.")
    issues = _words(result)
    assert issues["recieve"]["category"] == "misspelling"
    assert "receive" in issues["recieve"]["suggestions"]


def test_preserves_case():
    result = check_spelling("Color is nice. ORGANIZE now.")
    issues = _words(result)
    assert issues["Color"]["suggestions"] == ["Colour"]
    assert issues["ORGANIZE"]["suggestions"] == ["ORGANISE"]


def test_ignores_numbers_and_empty():
    assert check_spelling("")["ok"]
    assert check_spelling("Meet at 3pm on level 2.")["ok"]
