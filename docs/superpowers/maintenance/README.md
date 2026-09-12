# Maintenance Guides

Targeted documentation for agents working on specific subsystems without reading the entire codebase.

## Guides

| Doc | Target Area |
|-----|-------------|
| [harness-maintenance.md](./harness-maintenance.md) | `src/lingua/agent/harness.py` — voice loop orchestration |
| [tutor-maintenance.md](./tutor-maintenance.md) | `src/lingua/tutor.py` + `src/lingua/prompts/tutor.py` — LLM integration |
| [asr-tts-maintenance.md](./asr-tts-maintenance.md) | `src/lingua/asr.py`, `audio_loop.py`, `voice_studio.py` — voice pipeline |
| [recorder-debug-guide.md](./recorder-debug-guide.md) | Session log analysis — `data/sessions/session_*.json` |

## Related Docs

- [Code Review (bugs M2, M5, M6, E, B, A, D)](../specs/2026-09-09-code-review.md)
- [Current Architecture](../specs/2026-09-09-current-architecture.md)
- [Conversational Harness Spec](../specs/2026-09-09-conversational-harness.md)

## Quick Navigation

```
docs/superpowers/
├── maintenance/
│   ├── README.md           ← You are here
│   ├── harness-maintenance.md
│   ├── tutor-maintenance.md
│   ├── asr-tts-maintenance.md
│   └── recorder-debug-guide.md
└── specs/
    ├── 2026-09-09-code-review.md
    └── 2026-09-09-current-architecture.md
```
