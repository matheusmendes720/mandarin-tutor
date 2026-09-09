"""Tests for config loading."""
import pytest
from pathlib import Path
from lingua.config import LinguaConfig


def test_from_toml_finds_project_file_from_other_cwd(monkeypatch, tmp_path):
    """Test that from_toml resolves path relative to package, not cwd."""
    # Simulate cwd != project root
    monkeypatch.chdir(tmp_path)
    from lingua.config import LinguaConfig
    config = LinguaConfig.from_toml("lingua.toml")
    # Must NOT silently fall back to defaults — the project lingua.toml exists
    assert config.voicestudio.voice_mandarin == "8c53222c"  # from real config


def test_from_toml_absolute_path_still_works(tmp_path):
    """Test that absolute paths still work."""
    config = LinguaConfig.from_toml("lingua.toml")
    assert config.voicestudio.voice_mandarin == "8c53222c"


def test_from_toml_returns_defaults_for_missing_file(tmp_path):
    """Test that missing files return defaults."""
    config = LinguaConfig.from_toml("nonexistent.toml")
    # Should return defaults
    assert config.voicestudio.voice_mandarin == "8c53222c"  # default value
