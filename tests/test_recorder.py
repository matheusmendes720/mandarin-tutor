"""Tests for SessionRecorder."""
import json
import tempfile
from pathlib import Path

from lingua.recorder import SessionRecorder, Turn


def test_recorder_writes_json_per_session(tmp_path: Path):
    rec = SessionRecorder(tmp_path)
    rec.start(input_device="Mic", output_device="HP")
    rec.record_turn(Turn(
        ts=1.0, seq=1, asr_text="hello", asr_language="en",
        llm_response="hi", llm_latency_ms=1500,
    ))
    rec.record_turn(Turn(
        ts=2.0, seq=2, asr_text="你好", asr_language="zh",
        llm_response="你好", llm_latency_ms=1700,
    ))
    path = rec.finish()
    assert path is not None
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["session_id"]
    assert len(data["turns"]) == 2
    assert data["turns"][0]["seq"] == 1
    assert data["turns"][1]["seq"] == 2
    assert data["turns"][1]["asr_text"] == "你好"
    assert data["metadata"]["input_device"] == "Mic"
    assert data["metadata"]["n_turns"] == 2
    assert data["metadata"]["end_ts"] >= 0


def test_recorder_writes_empty_session(tmp_path: Path):
    """Even if no turns happen, the file should be written so we have evidence
    a session existed (e.g., for diagnosing crashes)."""
    rec = SessionRecorder(tmp_path)
    rec.start()
    path = rec.finish()
    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["turns"] == []
    assert data["metadata"]["n_turns"] == 0


def test_recorder_default_path_is_data_sessions():
    """Default path is data/sessions/."""
    rec = SessionRecorder()
    assert rec.path == Path("data/sessions")
    # Don't actually write — just check construction
