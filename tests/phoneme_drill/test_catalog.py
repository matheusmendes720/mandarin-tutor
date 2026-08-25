"""Tests for PinyinCompletoCatalog (PhonemeCatalog implementation)."""
from pathlib import Path

import pytest

from src.lingua.core.config import PhonemeCatalogConfig
from src.lingua.phoneme_drill.catalog import PinyinCompletoCatalog


@pytest.fixture
def catalog() -> PinyinCompletoCatalog:
    repo = Path(__file__).resolve().parents[2]
    return PinyinCompletoCatalog(
        PhonemeCatalogConfig(
            guia_path=str(repo / "pinyin-completo" / "guia.html"),
            audio_base=str(repo / "pinyin-completo" / "audio"),
        )
    )


def test_initials_returns_each_with_group(catalog):
    initials = catalog.initials()
    assert len(initials) == 21
    for entry in initials:
        assert {"key", "group", "name_pt", "audio_path"} <= set(entry.keys())
    assert any(entry["group"] != "Outros" for entry in initials), \
        "initials lost their parsed group — catalog regex regressed?"


def test_finals_returns_each_with_group(catalog):
    finals = catalog.finals()
    assert len(finals) == 39
    for entry in finals:
        assert {"key", "group", "name_pt", "audio_path"} <= set(entry.keys())
    assert any(entry["group"] != "Outros" for entry in finals), \
        "finals lost their parsed group — catalog regex regressed?"


def test_tones_returns_five(catalog):
    tones = catalog.tones()
    assert len(tones) == 5
    for entry in tones:
        assert {"number", "name_pt", "name_zh", "audio_path"} <= set(entry.keys())
        assert entry["audio_path"].endswith(f"ma{entry['number']}.wav")
