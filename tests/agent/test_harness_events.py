"""Tests for harness event publishing."""
import asyncio
from unittest.mock import MagicMock
from lingua.hud.events import (
    AsrFinalEvent, LlmStartEvent, LlmDoneEvent, TtsStartEvent, TtsDoneEvent
)
from lingua.hud.bus import EventBus
from lingua.agent.harness import VoiceAgentHarness


def test_harness_accepts_event_bus():
    bus = EventBus()
    # Just construction — doesn't actually run
    mock_tutor = MagicMock()
    harness = VoiceAgentHarness(tutor=mock_tutor, event_bus=bus)
    assert harness.event_bus is bus


def test_harness_event_bus_optional():
    mock_tutor = MagicMock()
    harness = VoiceAgentHarness(tutor=mock_tutor)
    assert harness.event_bus is None
