"""Tests for pronunciation scoring subsystem."""
import pytest


def test_levenshtein_distance_empty():
    """Levenshtein distance between empty sequences."""
    from lingua.pronunciation.scorer import levenshtein_distance

    assert levenshtein_distance([], []) == 0
    assert levenshtein_distance(["a"], []) == 1
    assert levenshtein_distance([], ["b"]) == 1


def test_levenshtein_distance_identical():
    """Levenshtein distance for identical sequences."""
    from lingua.pronunciation.scorer import levenshtein_distance

    assert levenshtein_distance(["a", "b", "c"], ["a", "b", "c"]) == 0


def test_levenshtein_distance_substitution():
    """Levenshtein distance with substitution."""
    from lingua.pronunciation.scorer import levenshtein_distance

    # One substitution
    assert levenshtein_distance(["a", "b"], ["a", "c"]) == 1


def test_levenshtein_distance_insertion():
    """Levenshtein distance with insertion."""
    from lingua.pronunciation.scorer import levenshtein_distance

    # One insertion
    assert levenshtein_distance(["a", "c"], ["a", "b", "c"]) == 1


def test_levenshtein_distance_deletion():
    """Levenshtein distance with deletion."""
    from lingua.pronunciation.scorer import levenshtein_distance

    # One deletion
    assert levenshtein_distance(["a", "b", "c"], ["a", "c"]) == 1


def test_levenshtein_distance_known_example():
    """Levenshtein distance on known example."""
    from lingua.pronunciation.scorer import levenshtein_distance

    # "kitten" -> "sitting" = 3
    # k i t t e n
    # s i t t i n g
    # Actually let's use phonemes
    assert levenshtein_distance(["k", "ae", "t"], ["k", "ae", "t"]) == 0


def test_compute_phoneme_score_identical():
    """Score is 1.0 for identical sequences."""
    from lingua.pronunciation.scorer import compute_phoneme_score

    assert compute_phoneme_score(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_compute_phoneme_score_completely_different():
    """Score is 0.0 for completely different sequences."""
    from lingua.pronunciation.scorer import compute_phoneme_score

    # All substitutions = 0.0
    assert compute_phoneme_score(["a", "b"], ["x", "y"]) == 0.0


def test_compute_phoneme_score_partial():
    """Score is partial for partial matches."""
    from lingua.pronunciation.scorer import compute_phoneme_score

    # 1 error in 3 = 1 - 1/3 = 0.666...
    score = compute_phoneme_score(["a", "b", "c"], ["a", "x", "c"])
    assert score == pytest.approx(0.666, rel=0.01)


def test_compute_phoneme_score_empty_expected():
    """Score handles empty expected sequence."""
    from lingua.pronunciation.scorer import compute_phoneme_score

    assert compute_phoneme_score([], []) == 1.0
    assert compute_phoneme_score([], ["a"]) == 0.0


def test_align_phonemes_all_match():
    """Align phonemes when all match."""
    from lingua.pronunciation.scorer import align_phonemes

    result = align_phonemes(["a", "b", "c"], ["a", "b", "c"])
    # All match means no errors
    assert len(result) == 0


def test_align_phonemes_with_mismatches():
    """Align phonemes with some mismatches."""
    from lingua.pronunciation.scorer import align_phonemes

    result = align_phonemes(["a", "b", "c"], ["a", "x", "c"])
    # Should return indices where expected != actual
    positions = [pos for pos, label in result]
    assert 1 in positions


def test_align_phonemes_extra_expected():
    """Align when expected has extra phonemes."""
    from lingua.pronunciation.scorer import align_phonemes

    result = align_phonemes(["a", "b", "c"], ["a", "b"])
    # Should mark the extra phoneme as error
    assert len(result) == 1


def test_default_phoneme_analyzer_analyze():
    """DefaultPhonemeAnalyzer.analyze returns list[str]."""
    from lingua.pronunciation.scorer import DefaultPhonemeAnalyzer

    analyzer = DefaultPhonemeAnalyzer()
    result = analyzer.analyze("hello")
    assert isinstance(result, list)
    assert all(isinstance(p, str) for p in result)


def test_default_phoneme_analyze_returns_phonemes():
    """DefaultPhonemeAnalyzer.analyze returns phonemes for known text."""
    from lingua.pronunciation.scorer import DefaultPhonemeAnalyzer

    analyzer = DefaultPhonemeAnalyzer()
    # Test with a simple word - should return phonemes
    result = analyzer.analyze("hi")
    # Result should contain phoneme-like entries
    assert len(result) > 0
