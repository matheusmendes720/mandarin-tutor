from unittest.mock import patch, MagicMock
from lingua.tutor import MandarinTutor
from lingua.config import LinguaConfig


def test_ask_llm_uses_max_tokens_120():
    config = LinguaConfig.defaults()
    with patch("lingua.tutor.VoiceStudioClient"):
        tutor = MandarinTutor(config)
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
    mock_resp.raise_for_status = MagicMock()
    mock_session.post.return_value = mock_resp
    tutor._session = mock_session
    tutor._ask_llm("test")
    call_kwargs = mock_session.post.call_args.kwargs
    payload = call_kwargs["json"]
    assert payload["max_tokens"] == 120
