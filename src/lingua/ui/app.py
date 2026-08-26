"""Gradio app — unified language learning interface."""
import gradio as gr
from src.lingua.pronunciation.scorer import compute_phoneme_score, align_phonemes
from src.lingua.pronunciation.whisper_scoring import WhisperPhonemeScorer
from src.lingua.vocab.scheduler import Card, ReviewQuality, fsrs_schedule, create_card, get_due_cards
from src.lingua.vocab.store import JsonStore
from src.lingua.core.config import DeckConfig, PhonemeCatalogConfig
from src.lingua.vocab.decks import PalavrasEssenciaisDeck
from src.lingua.phoneme_drill.catalog import PinyinCompletoCatalog
from src.lingua.voice_agent.session import build_tutor_prompt, VoiceAgentConfig, Message, ConversationRole
from src.lingua.voice_agent.agent import VoiceSession
from src.lingua.phoneme_drill.drill import PhonemeDrill
from src.lingua.tts.engine import synthesize_text
from src.lingua.accent.detector import detect_accent

_store = JsonStore()
_active_cards: list[Card] = []
_review_queue: list[Card] = []
_whisper_scorer = WhisperPhonemeScorer()
_phoneme_drill = PhonemeDrill()
_phoneme_catalog = PinyinCompletoCatalog(PhonemeCatalogConfig())
_deck = PalavrasEssenciaisDeck(DeckConfig())
_voice_session: VoiceSession | None = None
_current_review_card: Card | None = None


def _render_deck_card_list(cards: list[dict]) -> str:
    """Render a list of deck cards as an HTML table with per-row audio."""
    if not cards:
        return "<p>No cards in this category.</p>"
    active_ids = {c.id for c in _active_cards}
    rows = ""
    for card in cards:
        card_id = card.get("id", "")
        hanzi = card.get("hanzi", "")
        pinyin = card.get("pinyin", "") or ""
        pt = card.get("pt", "")
        audio_path = _deck.audio_path(card_id) if card_id else None
        badge = " ✓" if card_id in active_ids else ""
        audio_btn = (
            f'<button onclick="'
            f'document.getElementById(\'audio_{card_id}\').play()'
            f'">🔊</button>'
            f'<audio id="audio_{card_id}" src="{audio_path or ""}"></audio>'
            if audio_path
            else ""
        )
        rows += f"""
<tr>
  <td style="padding:4px 8px">
    <strong style="font-size:1.1em">{hanzi}</strong>{badge}<br>
    <span style="color:#666;font-size:0.9em">{pinyin}</span><br>
    <span style="color:#444">{pt}</span>
  </td>
  <td style="padding:4px 8px;text-align:right;vertical-align:middle">
    {audio_btn}
  </td>
</tr>"""
    return f"""
<table style="width:100%;border-collapse:collapse;font-family:sans-serif">
  <tbody>{rows}</tbody>
</table>"""


def _card_audio_path(card: Card) -> str | None:
    """Derive audio path from card metadata.

    Prefer the explicit ``card.audio_path`` field (set during import).
    Fall back to the pe_<slug> convention for backwards compatibility.
    """
    if card.audio_path:
        return card.audio_path
    if card.id.startswith("pe_"):
        slug = card.id[3:]  # strip 'pe_' prefix
        return f"palavras-essenciais/audio/{slug}.mp3"
    return None


def _get_voice_status() -> str:
    """Get current voice session status."""
    global _voice_session
    if _voice_session is None:
        return "Not connected"
    if _voice_session.is_connected():
        return "Connected"
    return "Disconnected"


def _check_livekit_configured() -> bool:
    """Check if LiveKit is configured."""
    global _voice_session
    if _voice_session is None:
        _voice_session = VoiceSession(VoiceAgentConfig(language="zh"))
    return _voice_session.is_configured


def _load_cards() -> None:
    """Load cards from persistent store.

    On first run (empty store), no cards are auto-imported: users opt into
    deck cards via the deck browser's "Add to my cards" button.
    """
    global _active_cards
    loaded = _store.load()
    _active_cards.clear()
    _review_queue.clear()
    if loaded:
        _active_cards.extend(loaded)
    _review_queue.extend(get_due_cards(_active_cards))


_load_cards()


def _get_card_labels() -> list[str]:
    """Return labels for all active cards."""
    return [f"{c.front} → {c.back}" for c in _active_cards]


def _get_queue_labels() -> list[str]:
    """Return labels for due cards."""
    return [f"{c.front} (due)" for c in _review_queue]


def score_pronunciation(audio, text: str) -> str:
    """Score pronunciation against target text using Whisper + g2p."""
    if audio is None:
        return "Please record audio first."
    if not text:
        return "Please enter target text to score against."
    try:
        result = _whisper_scorer.score(audio, text)
        if "error" in result:
            return f"Error: {result.get('error', 'Unknown error')}"
        score = result["score"]
        transcription = result["transcription"]
        return f"Pronunciation score: {score}% — transcribed: '{transcription}'"
    except Exception as e:
        return f"Error scoring pronunciation: {e}"


def play_tts(text: str) -> str:
    """Synthesize text to speech and return the audio file path."""
    if not text:
        return ""
    try:
        result = synthesize_text(text)
        import tempfile, os
        from scipy.io import wavfile
        import numpy as np
        # Write synthesized audio to a temp WAV file for Gradio to play
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "lingua_tts_output.wav")
        wav_data = np.frombuffer(result.audio_bytes, dtype=np.int16)
        wavfile.write(temp_path, result.sample_rate, wav_data)
        return temp_path
    except Exception as e:
        return f"TTS error: {e}"


def analyze_accent(audio_path: str | None) -> str:
    """Analyze accent from recorded audio."""
    if audio_path is None:
        return "Please record audio first."
    try:
        result = detect_accent(audio_path)
        if "error" in result:
            return f"Error: {result.get('error', 'Unknown error')}"
        return (
            f"Language: {result['language']}\n"
            f"Dialect: {result.get('dialect', 'N/A')}\n"
            f"Confidence: {result['confidence']:.0%}\n"
            f"Transcription: {result.get('transcription', 'N/A')}"
        )
    except Exception as e:
        return f"Accent analysis error: {e}"


def add_flashcard(front: str, back: str) -> tuple[list[dict], list[dict]]:
    card = create_card(id=str(len(_active_cards) + 1), front=front, back=back)
    _active_cards.append(card)
    _review_queue.extend(get_due_cards([card]))
    _store.save(_active_cards)
    return [_card_to_display_dict(c) for c in _active_cards], [_card_to_display_dict(c) for c in _review_queue]


def _card_to_display_dict(card: Card) -> dict:
    """Convert a Card to a display-friendly dict for gr.JSON."""
    audio = _card_audio_path(card)
    return {
        "id": card.id,
        "front": card.front,
        "back": card.back,
        "pinyin": card.pinyin,
        "context": card.context,
        "cat": card.cat,
        "tones": card.tones,
        "due": card.due_date.isoformat() if card.due_date else None,
        "interval": card.interval_days,
        "audio": "🔊" if audio else None,
    }


def list_deck_cards(category_key: str | None) -> str:
    cards = _deck.cards_by_category(category_key)
    return _render_deck_card_list(cards)


def list_deck_categories() -> list[dict]:
    """Return deck category metadata."""
    return _deck.categories()


def play_deck_card_audio(card_id: str) -> str | None:
    """Return audio path for a given deck card_id."""
    return _deck.audio_path(card_id)


def load_card_lists() -> tuple[list[dict], list[dict]]:
    """Load card lists for gr.JSON display on app startup."""
    return [_card_to_display_dict(c) for c in _active_cards], [_card_to_display_dict(c) for c in _review_queue]


def review_card(quality_str: str) -> str:
    """Review a due card and return updated status."""
    global _current_review_card
    if not _review_queue:
        _current_review_card = None
        return "No cards due!"
    _current_review_card = _review_queue[0]
    card = _review_queue.pop(0)
    q = ReviewQuality[quality_str.upper()]
    updated = fsrs_schedule(card, q)
    for i, c in enumerate(_active_cards):
        if c.id == updated.id:
            _active_cards[i] = updated
    _review_queue.extend(get_due_cards([updated]))
    _store.save(_active_cards)
    return f"Reviewed: {updated.front} → next due in {updated.interval_days} days."


def play_card_audio() -> str | None:
    """Return the audio file path for the current review card."""
    if _current_review_card is None:
        return None
    return _card_audio_path(_current_review_card)


def connect_voice_session(scenario: str = "conversation") -> tuple[str, str]:
    """Connect to voice session for practice.

    Args:
        scenario: Practice scenario (conversation, pronunciation, dialogue)

    Returns:
        Tuple of (status message, button label)
    """
    global _voice_session
    try:
        if not _check_livekit_configured():
            return "LiveKit not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET.", "Connect"
        # Create session with Mandarin context
        config = VoiceAgentConfig(
            language="zh",
            system_prompt=f"""你是友好的普通话教师，帮助学生练习中文。
当前练习模式: {scenario}
- conversation (对话): 自由对话练习
- pronunciation (发音): 专注发音纠正
- dialogue (对话): 特定场景对话练习

请用中文回复，并根据模式提供适当的练习指导。"""
        )
        _voice_session = VoiceSession(config)
        import asyncio
        asyncio.get_event_loop().run_until_complete(_voice_session.connect())
        mode_text = {"conversation": "对话模式", "pronunciation": "发音模式", "dialogue": "情景对话"}
        return f"Connected - {mode_text.get(scenario, scenario)}", "Disconnect"
    except ImportError as e:
        return f"Error: {e}", "Connect"
    except RuntimeError as e:
        return f"Error: {e}", "Connect"
    except Exception as e:
        return f"Connection failed: {e}", "Connect"


def disconnect_voice_session() -> tuple[str, str]:
    """Disconnect from voice session.

    Returns:
        Tuple of (status message, button label)
    """
    global _voice_session
    try:
        if _voice_session is not None:
            import asyncio
            asyncio.get_event_loop().run_until_complete(_voice_session.disconnect())
            _voice_session = None
        return "Disconnected", "Connect"
    except Exception as e:
        return f"Disconnect error: {e}", "Connect"


def build_app(config: dict | None = None) -> gr.Blocks:
    global _active_cards, _review_queue
    if config is None:
        config = {}

    # Load persisted cards on startup
    _active_cards = _store.load()
    _review_queue = _active_cards  # review queue shares the same list reference

    app = gr.Blocks()
    with app:
        gr.Markdown("# 🌐 Lingua — Pronunciation & Vocabulary Tutor")

        with gr.Tabs():
            with gr.TabItem("🎤 Pronunciation"):
                with gr.Row():
                    with gr.Column():
                        text_input = gr.Textbox(label="Target phrase", placeholder="Type the phrase you want to practice...")
                        audio_input = gr.Audio(sources=["microphone"], type="filepath", label="Record your pronunciation")
                        score_btn = gr.Button("Score Pronunciation", variant="primary")
                        feedback_output = gr.Textbox(label="Feedback", lines=4)
                    with gr.Column():
                        tts_text = gr.Textbox(label="Phrase to hear", value="Hello, how are you today?")
                        tts_btn = gr.Button("🔊 Play TTS")
                        tts_output = gr.Audio(label="TTS Output")
                score_btn.click(fn=score_pronunciation, inputs=[audio_input, text_input], outputs=[feedback_output])
                tts_btn.click(fn=play_tts, inputs=[tts_text], outputs=[tts_output])

            with gr.TabItem("📚 Vocabulary"):
                gr.Markdown("### Browse the palavras-essenciais deck or review due cards.")
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### Add Flashcard")
                        new_front = gr.Textbox(label="Front (word/phrase)")
                        new_back = gr.Textbox(label="Back (translation/meaning)")
                        add_btn = gr.Button("Add Flashcard", variant="primary")
                        card_list = gr.JSON(label="All Cards")
                        queue_list = gr.JSON(label="Due for Review")
                    with gr.Column():
                        gr.Markdown("#### Review")
                        review_quality = gr.Radio(
                            choices=["again", "hard", "good", "easy"],
                            label="How well did you remember?",
                        )
                        review_btn = gr.Button("Submit Review")
                        review_status = gr.Textbox(label="Status", lines=2)
                        play_audio_btn = gr.Button("🔊 Play Audio", variant="secondary")
                        review_audio = gr.Audio(label="Audio", type="filepath")

                with gr.Accordion(f"📚 palavras-essenciais deck ({len(_deck.cards_by_category())} cards)", open=True):
                    _cat_choices = ["(all)"] + [c["name_pt"] for c in _deck.categories()]
                    _cat_by_label: dict[str, str | None] = {"(all)": None}
                    _cat_by_label.update({c["name_pt"]: c["key"] for c in _deck.categories()})
                    category_dropdown = gr.Dropdown(
                        choices=_cat_choices,
                        value="(all)",
                        label="Filter by category",
                    )
                    deck_card_audio = gr.Audio(label="Selected card audio", type="filepath")
                    deck_list = gr.HTML(label="Cards in selected category", value="")
                    with gr.Row():
                        prev_card_btn = gr.Button("⬅ Previous")
                        next_card_btn = gr.Button("Next ➡")
                        add_to_my_cards_btn = gr.Button("➕ Add to my cards", variant="primary")
                    add_to_my_cards_status = gr.Textbox(label="Status", interactive=False)
                    deck_index = gr.State(value=0)

                    def _on_category_change(label: str) -> tuple[str, int]:
                        key = _cat_by_label.get(label)
                        return _render_deck_card_list(_deck.cards_by_category(key)), 0

                    def _navigate(label: str, index: int, direction: int) -> tuple[str | None, int]:
                        key = _cat_by_label.get(label)
                        cards = _deck.cards_by_category(key)
                        if not cards:
                            return None, 0
                        new_index = (index + direction) % len(cards)
                        return play_deck_card_audio(cards[new_index]["id"]), new_index

                    def add_deck_card_to_my_cards(
                        category_label: str, index: int
                    ) -> tuple[str, list[dict], list[dict], str]:
                        """Idempotently add the currently-focused deck card to the active card store."""
                        from datetime import datetime
                        key = _cat_by_label.get(category_label)
                        cards = _deck.cards_by_category(key)
                        if not cards or index < 0 or index >= len(cards):
                            cards_out, queue_out = load_card_lists()
                            return _render_deck_card_list(_deck.cards_by_category(key)), cards_out, queue_out, "No card selected."
                        card_id = cards[index]["id"]
                        existing_ids = {c.id for c in _active_cards}
                        if card_id in existing_ids:
                            cards_out, queue_out = load_card_lists()
                            return _render_deck_card_list(_deck.cards_by_category(key)), cards_out, queue_out, f"Already in your cards: {card_id}"
                        deck_card = _deck.card(card_id)
                        if not deck_card:
                            cards_out, queue_out = load_card_lists()
                            return _render_deck_card_list(_deck.cards_by_category(key)), cards_out, queue_out, f"Card not found in deck: {card_id}"
                        new_card = Card(
                            id=deck_card["id"],
                            front=deck_card["hanzi"],
                            back=deck_card["pt"],
                            pinyin=deck_card["pinyin"],
                            context=deck_card["context"],
                            cat=deck_card["cat"],
                            tones=deck_card["tones"],
                            audio_path=deck_card["audio_path"],
                            due_date=datetime.now(),
                            ease_factor=2.5,
                            interval_days=0,
                            repetitions=0,
                        )
                        _active_cards.append(new_card)
                        _store.save(_active_cards)
                        cards_out, queue_out = load_card_lists()
                        return _render_deck_card_list(_deck.cards_by_category(key)), cards_out, queue_out, f"Added: {deck_card['hanzi']} ({deck_card['pinyin']})"

                    category_dropdown.change(
                        fn=_on_category_change,
                        inputs=[category_dropdown],
                        outputs=[deck_list, deck_index],
                    )
                    prev_card_btn.click(
                        fn=lambda label, idx: _navigate(label, idx, -1),
                        inputs=[category_dropdown, deck_index],
                        outputs=[deck_card_audio, deck_index],
                    )
                    next_card_btn.click(
                        fn=lambda label, idx: _navigate(label, idx, +1),
                        inputs=[category_dropdown, deck_index],
                        outputs=[deck_card_audio, deck_index],
                    )
                    add_to_my_cards_btn.click(
                        fn=add_deck_card_to_my_cards,
                        inputs=[category_dropdown, deck_index],
                        outputs=[deck_list, card_list, queue_list, add_to_my_cards_status],
                    )

                add_btn.click(fn=add_flashcard, inputs=[new_front, new_back], outputs=[card_list, queue_list])
                review_btn.click(fn=review_card, inputs=[review_quality], outputs=[review_status])
                play_audio_btn.click(fn=play_card_audio, outputs=[review_audio])
                app.load(fn=load_card_lists, outputs=[card_list, queue_list])
                app.load(
                    fn=lambda: (_render_deck_card_list(_deck.cards_by_category()), None),
                    outputs=[deck_list, deck_index],
                )

            with gr.TabItem("🗣️ Accent Analysis"):
                accent_audio = gr.Audio(sources=["microphone"], type="filepath", label="Speak to analyze accent")
                accent_btn = gr.Button("Analyze Accent", variant="primary")
                accent_output = gr.Textbox(label="Accent Result", lines=5)
                accent_btn.click(fn=analyze_accent, inputs=[accent_audio], outputs=[accent_output])

            with gr.TabItem("🔤 Phoneme Drills"):
                gr.Markdown("### Chinese Pinyin Audio Drills")
                gr.Markdown("Practice Mandarin tones and phoneme combinations using the pinyin-completo corpus.")
                with gr.Row():
                    with gr.Column():
                        initial_dropdown = gr.Dropdown(
                            choices=_phoneme_catalog.initials() or _phoneme_drill.list_initials(),
                            label="Initial (声母)",
                            value="m",
                        )
                        final_dropdown = gr.Dropdown(
                            choices=_phoneme_catalog.finals() or _phoneme_drill.list_finals(),
                            label="Final (韵母)",
                            value="a",
                        )
                        tone_slider = gr.Slider(
                            minimum=1,
                            maximum=5,
                            step=1,
                            value=1,
                            label="Tone (声调)",
                            interactive=True,
                        )
                        tone_display = gr.Textbox(
                            value="Tone 1 - 阴平 (alto e nivelado)",
                            label="Selected Tone",
                            interactive=False,
                        )
                        speed_radio = gr.Radio(
                            choices=[("1.0x", "1.0"), ("0.7x", "0.7"), ("1.3x", "1.3")],
                            value="1.0",
                            label="Playback speed (informational)",
                        )
                        play_btn = gr.Button("🔊 Play Audio", variant="primary")
                    with gr.Column():
                        phoneme_output = gr.Audio(label="Phoneme Audio")
                        tone_output = gr.Audio(label="Tone Audio")
                        combined_output = gr.Audio(label="Combined Audio")
                        gr.Markdown("#### Tone reference")
                        tone_info = gr.JSON(value=_phoneme_catalog.tones(), label="Tones (1-5)")
                with gr.Accordion("📂 Browse phonemes by group", open=True):
                    initials_browser = gr.JSON(value=_phoneme_catalog.initials(), label="Initials (声母)")
                    finals_browser = gr.JSON(value=_phoneme_catalog.finals(), label="Finals (韵母)")

                def update_tone_display(tone: int) -> str:
                    tone_names = {1: "Tone 1 - 阴平 (alto e nivelado)", 2: "Tone 2 - 阳平 (ascendente)", 3: "Tone 3 - 上声 (mergulhante)", 4: "Tone 4 - 去声 (descendente)", 5: "Tone 5 - 轻声 (neutro)"}
                    return tone_names.get(tone, f"Tone {tone}")

                def play_phoneme_audio(initial: str, final: str, tone: int) -> tuple[str | None, str | None, str | None]:
                    """Play phoneme + tone audio using the combined lookup."""
                    result = _phoneme_drill.play_phoneme_combined(
                        initial or None, final or None, tone
                    )
                    if not result:
                        return None, None, None
                    phoneme_paths, tone_path, _combined = result
                    phoneme_str = str(phoneme_paths[0]) if phoneme_paths else None
                    tone_str = str(tone_path) if tone_path else None
                    return phoneme_str, tone_str, phoneme_str

                tone_slider.change(fn=update_tone_display, inputs=[tone_slider], outputs=[tone_display])
                play_btn.click(
                    fn=play_phoneme_audio,
                    inputs=[initial_dropdown, final_dropdown, tone_slider],
                    outputs=[phoneme_output, tone_output, combined_output],
                )

            with gr.TabItem("💬 Voice Practice"):
                gr.Markdown("### 🇨🇳 普通话练习 - Mandarin Practice")
                gr.Markdown("Connect to voice tutor for conversational Mandarin practice.")

                with gr.Row():
                    with gr.Column():
                        scenario_dropdown = gr.Dropdown(
                            choices=["conversation", "pronunciation", "dialogue"],
                            label="Practice Mode 练习模式",
                            value="conversation",
                        )
                        voice_status = gr.Textbox(
                            label="Session Status 会话状态",
                            value="Not connected",
                            interactive=False
                        )
                        voice_connect_btn = gr.Button("Connect 连接", variant="primary")
                    with gr.Column():
                        voice_info = gr.Markdown("""
**Mandarin Practice Modes:**
- **对话 (Conversation)**: Free-talking practice
- **发音 (Pronunciation)**: Focus on pronunciation correction
- **情景对话 (Dialogue)**: Role-play specific scenarios

*Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET to connect.*
                        """)

                # Handle connect/disconnect toggle
                def toggle_voice_connection(scenario: str, current_btn: str) -> tuple[str, str]:
                    """Toggle voice connection on/off."""
                    if current_btn == "Disconnect":
                        return disconnect_voice_session()
                    return connect_voice_session(scenario)

                voice_connect_btn.click(
                    fn=toggle_voice_connection,
                    inputs=[scenario_dropdown, voice_connect_btn],
                    outputs=[voice_status, voice_connect_btn],
                )

        gr.Markdown("--- Built with Lingua Platform · AI Language Tutor ---")
    return app


if __name__ == "__main__":
    app = build_app()
    app.launch()
