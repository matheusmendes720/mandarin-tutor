"""Regression: stream_response must extract the 'text' field from JSON before
splitting on sentence boundaries — otherwise the JSON syntax punctuation
(",", ":", etc.) inside the response would be treated as sentence ends."""
from unittest.mock import patch

from lingua.tutor import MandarinTutor
from lingua.config import LinguaConfig


def test_stream_response_splits_text_field_not_json_syntax():
    config = LinguaConfig.defaults()
    tutor = MandarinTutor(config)

    # LLM streams valid JSON with sentence-ending punctuation INSIDE the
    # "text" field. Naive splitting would cut at every "!" or "。" anywhere
    # in the response including inside JSON syntax.
    json_response = '{"type":"dialogue","text":"Nǐ hǎo! 你好！","expected":"","feedback":""}'
    fake_lines = [
        ('data: {"choices": [{"delta": {"content": "' + json_escape_chunk(json_response) + '"}}]}').encode("utf-8"),
        b"data: [DONE]",
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

    # The text field contains "Nǐ hǎo! 你好！" — two sentences.
    assert full == json_response
    # Sentences come from the "text" field only, so we expect them split on
    # the embedded ！. (The "!" inside "Nǐ hǎo!" is also a boundary.)
    assert len(sentences) >= 1, f"expected at least 1 sentence, got {sentences!r}"
    # No raw JSON syntax (commas, braces) should appear in the sentences.
    for s in sentences:
        assert "{" not in s, f"sentence contains JSON syntax: {s!r}"
        assert "," not in s, f"sentence contains JSON comma: {s!r}"


def json_escape_chunk(text: str) -> str:
    """Escape a chunk for embedding inside an SSE data: line that itself is
    wrapped in double quotes."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
