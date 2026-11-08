from australian_writing.readability import get_reading_level


def test_empty_text():
    result = get_reading_level("   ")
    assert result["australian_year_level"] is None


def test_simple_text_low_year_level():
    result = get_reading_level("The cat sat. The dog ran. We had fun.")
    assert result["flesch_kincaid_grade"] is not None
    assert result["australian_year_level"].startswith(("Foundation", "Year"))


def test_complex_text_higher_grade():
    simple = get_reading_level("I see a cat. It is fun. We run.")
    complex_ = get_reading_level(
        "The epistemological ramifications of phenomenological inquiry "
        "necessitate rigorous methodological reconsideration throughout."
    )
    assert complex_["flesch_kincaid_grade"] > simple["flesch_kincaid_grade"]


def test_deterministic():
    text = "Australia is a large country with diverse ecosystems."
    assert get_reading_level(text) == get_reading_level(text)


def test_reading_age_present():
    result = get_reading_level("The quick brown fox jumps over the lazy dog.")
    assert isinstance(result["reading_age_years"], int)
