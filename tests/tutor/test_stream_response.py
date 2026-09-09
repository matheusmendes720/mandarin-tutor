"""Regression: stream_response must emit the final buffered text even when
the LLM ends without a sentence delimiter."""
from unittest.mock import patch, MagicMock

import pytest

from lingua.tutor import MandarinTutor, find_sentence_boundary
from lingua.config import LinguaConfig


def test_find_sentence_boundary_returns_none_when_no_delimiter():
    """Sanity: helper itself doesn't invent delimiters."""
    assert find_sentence_boundary("hello there", 0) is None
    assert find_sentence_boundary("你好", 0) is None


def test_stream_response_emits_remainder_without_delimiter():
    """If LLM ends with '你好' (no punctuation), stream_response should still
    emit it as the final sentence so the harness can speak it."""
    config = LinguaConfig.defaults()
    tutor = MandarinTutor(config)
    # Mock the HTTP response to return a tiny SSE stream with no delimiter.
    fake_lines = [
        b'data: {"choices": [{"delta": {"content": "\xe4\xbd\xa0\xe5\xa5\xbd"}}]}',
        b'',  # blank separator
        b'data: [DONE]',
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(fake_lines)

    with patch.object(tutor._session, "post", return_value=FakeResp()):
        full, sentences = tutor.stream_response(
            [{"role": "user", "content": "test"}]
        )

    assert full == "你好"
    assert sentences == ["你好"], f"expected ['你好'], got {sentences!r}"


def test_stream_response_emits_partial_then_remainder():
    """If LLM streams '你好' (no delim) followed by '！' (delim), the final
    sentence must include both parts."""
    config = LinguaConfig.defaults()
    tutor = MandarinTutor(config)

    fake_lines = [
        b'data: {"choices": [{"delta": {"content": "\xe4\xbd\xa0\xe5\xa5\xbd"}}]}',
        b'data: {"choices": [{"delta": {"content": "\xef\xbc\x81"}}]}',
        b'data: [DONE]',
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(fake_lines)

    with patch.object(tutor._session, "post", return_value=FakeResp()):
        full, sentences = tutor.stream_response(
            [{"role": "user", "content": "test"}]
        )

    assert full == "你好！"
    # Boundary detected on ！ emits '你好！'
    assert sentences == ["你好！"], f"expected ['你好！'], got {sentences!r}"
