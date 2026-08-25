"""Chinese phoneme audio drills using pinyin-completo audio files."""
from pathlib import Path
from typing import Literal


# Base path for pinyin-completo audio files
AUDIO_BASE = Path(__file__).parent.parent.parent.parent / "pinyin-completo" / "audio"
INITIALS_DIR = AUDIO_BASE / "iniciais"
FINALS_DIR = AUDIO_BASE / "finais"
TONES_DIR = AUDIO_BASE / "tonalidades"


# Mapping from tone number to filename
TONE_FILES: dict[int, str] = {
    1: "ma1.wav",
    2: "ma2.wav",
    3: "ma3.wav",
    4: "ma4.wav",
    5: "ma5.wav",
}


class PhonemeDrill:
    """Maps Chinese pinyin phonemes to audio file paths.

    Provides audio playback for Chinese pinyin initials, finals, and tones
    using the pinyin-completo audio files.
    """

    def __init__(self) -> None:
        self._initials_cache: list[str] | None = None
        self._finals_cache: list[str] | None = None

    def _load_initials(self) -> list[str]:
        """Load available initials from the audio directory."""
        if self._initials_cache is None:
            if INITIALS_DIR.exists():
                self._initials_cache = [
                    f.stem for f in INITIALS_DIR.glob("*.wav")
                ]
            else:
                self._initials_cache = []
        return self._initials_cache

    def _load_finals(self) -> list[str]:
        """Load available finals from the audio directory."""
        if self._finals_cache is None:
            if FINALS_DIR.exists():
                self._finals_cache = [
                    f.stem for f in FINALS_DIR.glob("*.wav")
                ]
            else:
                self._finals_cache = []
        return self._finals_cache

    def list_initials(self) -> list[str]:
        """Return all available initial keys."""
        return self._load_initials()

    def list_finals(self) -> list[str]:
        """Return all available final keys."""
        return self._load_finals()

    def _split_phoneme(
        self, phoneme: str
    ) -> tuple[str | None, str | None]:
        """Split a pinyin phoneme into initial and final.

        Args:
            phoneme: A pinyin syllable like "ma", "ni", "hao"

        Returns:
            Tuple of (initial, final) or (None, None) if parsing fails
        """
        if not phoneme:
            return None, None

        phoneme = phoneme.lower().strip()

        # Check if it's a combined initial+final in our audio files
        initials = self._load_initials()
        finals = self._load_finals()

        # Try to find a matching initial
        for initial in sorted(initials, key=len, reverse=True):
            if phoneme.startswith(initial):
                remaining = phoneme[len(initial):]
                # Check if remaining is a valid final
                if remaining in finals:
                    return initial, remaining

        # No match found - return the whole thing as final
        if phoneme in finals:
            return None, phoneme
        if phoneme in initials:
            return phoneme, None

        return None, None

    def play_phoneme(self, phoneme: str) -> list[Path] | None:
        """Get audio file paths for a pinyin phoneme.

        Args:
            phoneme: A full pinyin like "ma", "ni", "hao"

        Returns:
            List of audio file paths (initial + final), or None if not found
        """
        if not phoneme:
            return None

        phoneme = phoneme.lower().strip()

        # Check if the full phoneme exists as a combined file
        combined_path = INITIALS_DIR / f"{phoneme}.wav"
        if combined_path.exists():
            return [combined_path]

        # Try to split into initial + final
        initial, final = self._split_phoneme(phoneme)
        if initial is None and final is None:
            return None

        paths: list[Path] = []
        if initial:
            initial_path = INITIALS_DIR / f"{initial}.wav"
            if initial_path.exists():
                paths.append(initial_path)
        if final:
            final_path = FINALS_DIR / f"{final}.wav"
            if final_path.exists():
                paths.append(final_path)

        return paths if paths else None

    def play_tone(self, tone: int) -> Path | None:
        """Get audio file path for a specific tone number.

        Args:
            tone: Tone number (1-5)

        Returns:
            Path to the tone audio file, or None if not found
        """
        if tone < 1 or tone > 5:
            return None

        tone_file = TONE_FILES.get(tone)
        if tone_file is None:
            return None

        tone_path = TONES_DIR / tone_file
        return tone_path if tone_path.exists() else None

    def play_phoneme_with_tone(
        self, phoneme: str, tone: int
    ) -> Path | None:
        """Get audio file path for a phoneme with specific tone.

        For tone-marked variants, looks for files like ma1.wav, ma2.wav, etc.
        in the tonalidades directory.

        Args:
            phoneme: Base pinyin phoneme (e.g., "ma", "ni")
            tone: Tone number (1-5)

        Returns:
            Path to the tone-marked audio file, or None if not found
        """
        if tone < 1 or tone > 5:
            return None

        # First try to find a direct tone-marked file
        tone_phoneme = f"{phoneme.lower().strip()}{tone}"
        tone_path = TONES_DIR / f"{tone_phoneme}.wav"
        if tone_path.exists():
            return tone_path

        # Fall back to combining the phoneme with tone audio
        # This is a pragmatic approach - return the tone reference
        tone_file = TONE_FILES.get(tone)
        if tone_file:
            return TONES_DIR / tone_file

        return None

    def get_tone_audio_path(self, tone: int) -> Path | None:
        """Get the audio path for a tone number.

        Args:
            tone: Tone number (1-5)

        Returns:
            Path to ma1.wav through ma5.wav
        """
        return self.play_tone(tone)

    def play_phoneme_combined(
        self, initial: str | None, final: str | None, tone: int
    ) -> tuple[list[Path], Path | None, list[Path]] | None:
        """Return (phoneme_paths, tone_path, combined_order).

        ``phoneme_paths`` lists the audio files for the initial + final
        (combined). ``tone_path`` is the ma{tone}.wav file, or None if the
        tone is invalid. ``combined_order`` is the playback order
        (initial/final then tone).

        Returns None when both initial and final were provided but neither
        resolved to an audio path. If either initial or final resolves
        (even partially) or only a tone is requested, the 3-tuple is
        returned with the missing parts empty/None.
        """
        had_phoneme_input = bool(initial or final)
        phoneme = (initial or "") + (final or "")
        phoneme_paths = self.play_phoneme(phoneme) if phoneme else None
        tone_path = self.play_tone(tone)
        # If the caller asked for a phoneme but we couldn't resolve it,
        # treat the call as invalid — don't leak a tone-only stub.
        if had_phoneme_input and not phoneme_paths:
            return None
        if not phoneme_paths and tone_path is None:
            return None
        ordered = list(phoneme_paths or [])
        if tone_path is not None:
            ordered.append(tone_path)
        return phoneme_paths or [], tone_path, ordered
