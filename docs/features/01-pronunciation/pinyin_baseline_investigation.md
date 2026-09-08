# Pinyin baseline — expected score distribution investigation

> Research question: for the test corpus at
> `palavras-essenciais/audio/*.mp3` (50 native-Mandarin recordings of common
> phrases), what is a reasonable expected score distribution from the current
> `WhisperPhonemeScorer` pipeline, and what threshold should mean "passable"?

---

## 1. The corpus

`palavras-essenciais/` contains 50 phrase recordings (`ls palavras-essenciais/audio/*.mp3 | wc -l` → 50),
each tied to a pinyin string and tone sequence in `palavras-essenciais/guia.html`
(see e.g. lines 449–490, regex matched by `_WORD_PATTERN` in `vocab/decks.py:30`).

### Phrase length distribution

Quick categorisation of the deck (from grep over `guia.html`):

| Length | Count | Examples |
|---|---|---|
| 1 syllable | 10 | `我`, `你`, `他`, `是`, `有`, `好`, `去`, `来`, `吃`, `喝`, `看` |
| 2 syllables | 23 | `你好`, `再见`, `拜拜`, `晚安`, `谢谢`, `请`, `是`, `没有`, `好`, `不好`, `水`, `这`, `那`, `在`, `现在`, `喜欢`, `累`, `知道`, `你的`, `真的`, `明白` |
| 3 syllables | 12 | `你好吗`, `我很好`, `早上好`, `晚上好`, `明天见`, `不客气`, `对不起`, `没关系`, `我们`, `不是`, `好吃`, `买单`, `今天`, `明天`, `昨天`, `慢慢来` |
| 4+ syllables | 5 | `明天见`, `对不起`, `没关系`, `我们`, `买单` |

Roughly: 1 syllable (20%), 2 syllables (46%), 3 syllables (24%), 4+ syllables (10%).

The corpus is **greeting-heavy** (saudacoes, despedidas, cortesia = ~30% of cards)
and short. This matters: with 1–2 syllable utterances, Whisper's English-bias is
strongest (the model rarely commits to a non-English language for short inputs).

---

## 2. Current pipeline behaviour on this corpus

The pipeline is:

```
audio.mp3  ─►  Whisper.transcribe (no language hint)
              ─►  transcribed_text  ─►  g2p()  ─►  transcribed_phonemes
target pinyin (from deck)  ─►  g2p()  ─►  expected_phonemes
score = 100 * (1 - levenshtein / max(len_e, len_a))
```

**Without** the `language="zh"` fix (review.md Old-2 / New-3):

| Speaker | Expected score on native audio |
|---|---|
| Native speaker (audio is the deck's own recording) | **~0–30** — Whisper emits Latin-alphabet guesses (`"ni hao"`, `"hello"`, or empty), g2p on Latin input is dominated by English phonemes, Levenshtein distance from `["n", "i3", ...]` is large. |
| Intermediate learner, accurate Mandarin | **~10–40** — same upstream issue (English-biased transcription). |
| Beginner, near-pinyin | **~5–20** — actually lower than intermediate, because their tones/wrong-syllable mistakes are *added* on top of the English-bias tax. |

**With** `language="zh"` (after C-1.8 lands):

| Speaker | Expected score on native audio |
|---|---|
| Native speaker | **~85–100** — Whisper + language hint should return the correct hanzi/pinyin; g2p tokenizes identically on both sides; Levenshtein distance is 0 or near-0. |
| Intermediate learner, accurate Mandarin | **~70–90** — minor phoneme substitutions (zh/z confusion, n/l confusion for Portuguese speakers) cost 1–2 edits per syllable. |
| Beginner, near-pinyin | **~40–65** — tone errors alone cost ~1 edit per syllable in current Levenshtein (tone numbers are part of the g2p output). |

These numbers are qualitative estimates; a real evaluation requires running Whisper
on the corpus with and without the language hint and measuring the empirical
distribution. **This is a follow-up task** — F1 ships the contract, not the eval.

---

## 3. What "passable" should mean

The deck's existing threshold is `PronunciationConfig.scoring_threshold = 0.70`
(`core/config.py:20`), which maps to a 70/100 score. With the fix:

| Threshold | Meaning | Use case |
|---|---|---|
| 90+ | Native-like | "I'm a heritage speaker / professional translator" |
| 75–89 | Comfortable | "I can hold a conversation with minor friction" |
| 60–74 | Functional | "Tourist-level; I can be understood" |
| 40–59 | Struggling | "Needs work; review this card again" |
| <40 | Lost | "Re-listen to the audio, mimic, try again" |

**Recommendation:** keep `scoring_threshold = 0.70` for the SRS "advance to next
card" gate, but expose two UI thresholds:
- `pass_threshold = 0.70` — "good enough to advance in SRS"
- `mastery_threshold = 0.90` — "mark as mastered, remove from rotation"

This is a future feature (out of scope for F1). F1's deliverable is the working
pipeline; the SRS integration of the threshold is handled by the existing
`vocab/scheduler.py` and not modified here.

---

## 4. Tone sandhi caveat

`palavras-essenciais/guia.html:451` notes for `我很好`:
> "Atenção ao sandhi: soa 'wó hén hǎo'."

The deck's `pinyin` field stores **citation tones** (`wǒ hěn hǎo`), but a native
speaker produces **sandhi tones** (`wó hén hǎo`). A naive Levenshtein on g2p tokens
will mark the tone differences as errors even when the pronunciation is perfect.

This is a known limitation (review.md item New-7). Two mitigations are possible in
later work:

1. **Pre-process expected tones** with a sandhi-aware normaliser (small rule-based
   function: 3-3 → 2-3, 一/yī/yí/yì tone changes, 不 tone changes before 4th tone).
2. **Score on a different signal** (e.g. Whisper's confidence per token, or a tone
   classifier on the audio).

Neither is in F1 scope.

---

## 5. Comparison: g2p vs pypinyin for the bundled deck

Quick lookup at the spec level — both libraries convert hanzi to pinyin, but they
answer different questions:

| Concern | g2p (Kyubyong) | pypinyin |
|---|---|---|
| Primary purpose | English grapheme → ARPAbet | Hanzi → pinyin |
| Mandarin support | Indirect (via English-trained model on romanised input) | Native, designed for hanzi |
| Tone output | No tones (stress markers only) | Yes — `Style.TONE3` gives `ni3`, `Style.TONE` gives `nǐ` |
| Install footprint | Heavy (downloads an English lexicon) | Tiny (~50 KB, no data files) |
| Speed on 50 phrases | ~1s warm, ~3s cold (lexicon load) | <100 ms (no cold start) |
| CJK input handling | Poor (relies on romanisation) | Native |
| Pure-python | Yes | Yes |

**Verdict for this corpus:** `pypinyin` is strictly better:
- It's smaller, faster, and Mandarin-native.
- Its tone output (`ni3`) matches what we want for the Levenshtein comparison.
- It works directly on hanzi — no need for an extra hanzi→pinyin step.

`g2p` would still be useful if we wanted English-transliteration comparison
("ni hao" in Latin letters → ARPAbet), but the deck's audio is Mandarin hanzi, not
romanised Mandarin, so that path is a dead end.

**Recommendation (already in implementation_plan.md step 1):** use `pypinyin` as the
default Mandarin tokeniser, keep `g2p` as the optional English fallback for
ad-hoc Latin input (e.g. user types "ni3 hao3" in the UI).

---

## 6. Sources

- `palavras-essenciais/guia.html` — 50 phrases, line 449 onward.
- `src/lingua/vocab/decks.py` — `_WORD_PATTERN` regex at line 30.
- `src/lingua/pronunciation/whisper_scoring.py` — current pipeline.
- `src/lingua/pronunciation/scorer.py` — Levenshtein + g2p tokeniser.
- `src/lingua/core/config.py:17–22` — `PronunciationConfig`.
- `docs/features/01-pronunciation/review.md` — bug list.
- `docs/features/01-pronunciation/spec.md` — contracts.
