"""Gradio app — unified language learning interface."""
import gradio as gr
from src.lingua.pronunciation.scorer import compute_phoneme_score, align_phonemes
from src.lingua.pronunciation.whisper_scoring import WhisperPhonemeScorer
from src.lingua.vocab.scheduler import Card, ReviewQuality, fsrs_schedule, create_card, get_due_cards
from src.lingua.vocab.store import JsonStore
from src.lingua.voice_agent.session import build_tutor_prompt, VoiceAgentConfig, Message, ConversationRole

_store = JsonStore()
_active_cards: list[Card] = []
_review_queue: list[Card] = []
_whisper_scorer = WhisperPhonemeScorer()


def _load_cards() -> None:
    """Load cards from persistent store on startup."""
    global _active_cards
    loaded = _store.load()
    _active_cards.clear()
    _active_cards.extend(loaded)
    _review_queue.clear()
    _review_queue.extend(get_due_cards(_active_cards))


_load_cards()


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


def add_flashcard(front: str, back: str) -> tuple[list[str], list[str]]:
    card = create_card(id=str(len(_active_cards) + 1), front=front, back=back)
    _active_cards.append(card)
    _review_queue.extend(get_due_cards([card]))
    _store.save(_active_cards)
    labels = [f"{c.front} → {c.back}" for c in _active_cards]
    queue_labels = [f"{c.front} (due)" for c in _review_queue]
    return labels, queue_labels


def review_card(quality_str: str) -> str:
    """Review a due card and return updated status."""
    if not _review_queue:
        return "No cards due!"
    card = _review_queue.pop(0)
    q = ReviewQuality[quality_str.upper()]
    updated = fsrs_schedule(card, q)
    for i, c in enumerate(_active_cards):
        if c.id == updated.id:
            _active_cards[i] = updated
    _review_queue.extend(get_due_cards([updated]))
    _store.save(_active_cards)
    return f"Reviewed: {updated.front} → next due in {updated.interval_days} days."


def build_app(config: dict | None = None) -> gr.Blocks:
    if config is None:
        config = {}
    with gr.Blocks(title=config.get("title", "Lingua")) as app:
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

            with gr.TabItem("📚 Vocabulary"):
                with gr.Row():
                    with gr.Column():
                        new_front = gr.Textbox(label="Front (word/phrase)")
                        new_back = gr.Textbox(label="Back (translation/meaning)")
                        add_btn = gr.Button("Add Flashcard", variant="primary")
                        card_list = gr.List(label="All Cards")
                        queue_list = gr.List(label="Due for Review")
                    with gr.Column():
                        gr.Markdown("### Review")
                        review_quality = gr.Radio(choices=["again", "hard", "good", "easy"], label="How well did you remember?")
                        review_btn = gr.Button("Submit Review")
                        review_status = gr.Textbox(label="Status", lines=2)
                add_btn.click(fn=add_flashcard, inputs=[new_front, new_back], outputs=[card_list, queue_list])
                review_btn.click(fn=review_card, inputs=[review_quality], outputs=[review_status])

            with gr.TabItem("🗣️ Accent Analysis"):
                accent_audio = gr.Audio(sources=["microphone"], type="filepath", label="Speak to analyze accent")
                accent_btn = gr.Button("Analyze Accent")
                accent_output = gr.JSON(label="Accent Result")

            with gr.TabItem("💬 Voice Practice"):
                gr.Markdown("Connect to voice tutor for conversational practice.")
                voice_status = gr.Textbox(label="Session Status", value="Not connected")
                voice_connect_btn = gr.Button("Start Voice Session", variant="primary")

        gr.Markdown("--- Built with Lingua Platform · AI Language Tutor ---")
    return app


if __name__ == "__main__":
    app = build_app()
    app.launch()
