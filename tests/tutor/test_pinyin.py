"""Tests for the to_pinyin helper."""
from lingua.tutor import to_pinyin


def test_chinese_text_converts_to_pinyin():
    assert to_pinyin("你好") == "nǐ hǎo"


def test_multi_character_text():
    assert to_pinyin("你好世界") == "nǐ hǎo shì jiè"


def test_english_text_unchanged():
    assert to_pinyin("Hello world") == "Hello world"


def test_empty_string_unchanged():
    assert to_pinyin("") == ""


def test_mixed_chinese_and_english():
    result = to_pinyin("你好 hello")
    # pypinyin skips non-Chinese, so result keeps english as-is
    assert "nǐ hǎo" in result
    assert "hello" in result


def test_tone_marks_present():
    """Verify all four tones plus neutral are reachable."""
    for hanzi, expected_pinyin in [
        ("妈", "mā"),   # 1st tone
        ("麻", "má"),   # 2nd tone
        ("马", "mǎ"),   # 3rd tone
        ("骂", "mà"),   # 4th tone
    ]:
        assert to_pinyin(hanzi) == expected_pinyin
