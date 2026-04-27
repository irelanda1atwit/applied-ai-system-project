"""
tests/test_ai_advisor.py — Automated tests for the AI advisor layer
====================================================================
All tests that touch PetCareAI mock the Anthropic client so no real API
calls are made. This keeps the suite fast, free, and deterministic.

Tests cover four verification categories:
  1. Automated output-format checks  — does the pipeline produce the right shape?
  2. Confidence scoring              — is CONFIDENCE present in task suggestions?
  3. Logging & error handling        — are calls/errors written to the log?
  4. Context builders                — do helper functions produce correct strings?

Run with:
    pytest tests/test_ai_advisor.py -v
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pawpal_system import CareTask, PetCareStats, OwnerStats, Priority
from ai_advisor import PetCareAI, _pet_context, _schedule_context
import ai_logger


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def dog():
    pet = PetCareStats(name="Mochi", species="dog", diet="grain-free")
    pet.add_medication("Apoquel 16mg")
    return pet


@pytest.fixture
def cat():
    return PetCareStats(name="Whiskers", species="cat")


@pytest.fixture
def owner(dog, cat):
    o = OwnerStats(name="Jordan", available_minutes=90, preferred_start_time="08:00")
    o.add_pet(dog)
    o.add_pet(cat)
    return o


@pytest.fixture
def sample_schedule(dog):
    tasks = [
        CareTask("Morning walk", 30, Priority.HIGH, "exercise"),
        CareTask("Feed Mochi",    5, Priority.HIGH, "feeding"),
    ]
    for t in tasks:
        dog.add_task(t)
    return tasks


# Builds a mock Anthropic response with the given reply text.
def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage   = MagicMock(input_tokens=120, output_tokens=80)
    return resp


# Standard TASK block the mock AI returns for suggest_tasks tests.
_TASK_BLOCK = (
    "TASK: Evening brush\n"
    "DURATION: 10\n"
    "PRIORITY: MEDIUM\n"
    "CATEGORY: grooming\n"
    "FREQUENCY: daily\n"
    "CONFIDENCE: HIGH\n"
    "REASON: Removes allergens from coat; especially important for dogs on Apoquel."
)


# ── 1. Context Builder Tests ───────────────────────────────────────────────────

class TestContextBuilders:

    def test_pet_context_contains_name_and_species(self, dog):
        ctx = _pet_context(dog)
        assert "Mochi" in ctx
        assert "dog"   in ctx

    def test_pet_context_contains_medication(self, dog):
        ctx = _pet_context(dog)
        assert "Apoquel 16mg" in ctx

    def test_pet_context_no_medications_shows_none(self, cat):
        ctx = _pet_context(cat)
        assert "none" in ctx.lower()

    def test_pet_context_lists_active_tasks_only(self, dog):
        t1 = CareTask("Walk",  20, Priority.HIGH)
        t2 = CareTask("Groom", 15, Priority.LOW)
        dog.add_task(t1)
        dog.add_task(t2)
        t1.mark_complete()
        ctx = _pet_context(dog)
        assert "Walk"  not in ctx   # completed — should be excluded
        assert "Groom" in ctx

    def test_pet_context_no_tasks_shows_none(self, cat):
        ctx = _pet_context(cat)
        assert "none" in ctx

    def test_schedule_context_empty_schedule_says_not_generated(self, owner):
        ctx = _schedule_context(owner, [])
        assert "not generated yet" in ctx

    def test_schedule_context_contains_owner_name(self, owner, sample_schedule):
        for t in sample_schedule:
            t.scheduled_time = None  # ensure no crash on missing time
        ctx = _schedule_context(owner, sample_schedule)
        assert "Jordan" in ctx

    def test_schedule_context_lists_task_titles(self, owner, sample_schedule):
        ctx = _schedule_context(owner, sample_schedule)
        assert "Morning walk" in ctx
        assert "Feed Mochi"   in ctx


# ── 2. PetCareAI Initialisation ───────────────────────────────────────────────

class TestPetCareAIInit:

    def test_raises_value_error_when_no_api_key(self):
        """Constructing PetCareAI without a key must raise immediately, not silently
        defer to the first API call."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY from the environment entirely
            import os
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            with patch.dict("os.environ", env, clear=True):
                with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                    PetCareAI(api_key="")

    def test_accepts_explicit_api_key(self):
        """Passing a key directly must not raise, regardless of the environment."""
        with patch("anthropic.Anthropic"):
            ai = PetCareAI(api_key="sk-test-key")
            assert ai is not None


# ── 3. Automated Output-Format Tests ─────────────────────────────────────────

class TestSuggestTasksOutput:

    def test_suggest_tasks_returns_non_empty_string(self, dog):
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            result = ai.suggest_tasks(dog)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_suggest_tasks_response_contains_task_keyword(self, dog):
        """The AI must produce output containing 'TASK:' — the structured format
        the system prompt enforces."""
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            result = ai.suggest_tasks(dog)
        assert "TASK:" in result

    def test_suggest_tasks_response_contains_priority(self, dog):
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            result = ai.suggest_tasks(dog)
        assert any(p in result for p in ("HIGH", "MEDIUM", "LOW"))

    def test_suggest_tasks_response_contains_duration(self, dog):
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            result = ai.suggest_tasks(dog)
        assert "DURATION:" in result

    def test_optimize_schedule_returns_non_empty_string(self, owner, sample_schedule):
        reply = "**Summary**\nGood coverage.\n\n**Improvements**\n1. Add litter scoop.\n\n**Critical gaps**\nNone."
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(reply)
            ai = PetCareAI(api_key="sk-test")
            result = ai.optimize_schedule(owner, sample_schedule)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_chat_returns_non_empty_string(self, owner):
        reply = "Dogs should be fed twice daily, once in the morning and once in the evening."
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(reply)
            ai = PetCareAI(api_key="sk-test")
            result = ai.chat("How often should I feed my dog?", owner=owner)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_chat_passes_history_to_api(self, owner):
        """Conversation history must be included in the messages list sent to the API,
        so the model has context from prior turns."""
        history = [
            {"role": "user",      "content": "What should I feed Mochi?"},
            {"role": "assistant", "content": "Grain-free kibble twice daily."},
        ]
        with patch("anthropic.Anthropic") as MockClient:
            mock_create = MockClient.return_value.messages.create
            mock_create.return_value = _mock_response("Follow-up answer.")
            ai = PetCareAI(api_key="sk-test")
            ai.chat("Any snack recommendations?", history=history, owner=owner)

        call_kwargs = mock_create.call_args.kwargs
        messages_sent = call_kwargs["messages"]
        # History (2) + new user message (1) = 3
        assert len(messages_sent) == 3
        assert messages_sent[0]["role"] == "user"
        assert messages_sent[1]["role"] == "assistant"
        assert messages_sent[2]["content"] == "Any snack recommendations?"


# ── 4. Confidence Scoring Tests ───────────────────────────────────────────────

class TestConfidenceScoring:

    def test_task_suggestion_contains_confidence_field(self, dog):
        """The system prompt requires a CONFIDENCE: field in every TASK block.
        This test verifies the mock output includes it and the pipeline doesn't
        strip it before returning."""
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            result = ai.suggest_tasks(dog)
        assert "CONFIDENCE:" in result

    def test_confidence_value_is_valid_level(self, dog):
        """CONFIDENCE must be one of HIGH, MEDIUM, or LOW — not a free-form string."""
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            result = ai.suggest_tasks(dog)
        assert any(f"CONFIDENCE: {level}" in result for level in ("HIGH", "MEDIUM", "LOW"))


# ── 5. Logging & Error Handling Tests ─────────────────────────────────────────

class TestLogging:

    def test_successful_call_writes_to_log(self, dog, tmp_path, monkeypatch):
        """A successful API call must create a log entry with ok=True."""
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            ai.suggest_tasks(dog)

        log_file = tmp_path / "ai_calls.jsonl"
        assert log_file.exists(), "log file must be created after a successful call"

        entry = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert entry["ok"]         is True
        assert entry["method"]     == "suggest_tasks"
        assert entry["error"]      is None
        assert entry["latency_ms"] >= 0  # mock calls complete in < 1 ms so 0.0 is valid

    def test_failed_call_writes_error_to_log(self, dog, tmp_path, monkeypatch):
        """When the API raises, the error must be logged before the exception
        propagates — no silent failures."""
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.side_effect = RuntimeError("API timeout")
            ai = PetCareAI(api_key="sk-test")
            with pytest.raises(RuntimeError):
                ai.suggest_tasks(dog)

        log_file = tmp_path / "ai_calls.jsonl"
        assert log_file.exists(), "log file must be created even on failure"

        entry = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert entry["ok"]    is False
        assert "API timeout"  in entry["error"]

    def test_multiple_calls_append_separate_entries(self, dog, tmp_path, monkeypatch):
        """Each call must append a new line — not overwrite the file."""
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            ai.suggest_tasks(dog)
            ai.suggest_tasks(dog)

        lines = (tmp_path / "ai_calls.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_log_entry_contains_token_counts(self, dog, tmp_path, monkeypatch):
        """Token counts from the API response must be recorded so usage can be
        monitored and costs estimated."""
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(_TASK_BLOCK)
            ai = PetCareAI(api_key="sk-test")
            ai.suggest_tasks(dog)

        entry = json.loads((tmp_path / "ai_calls.jsonl").read_text(encoding="utf-8").strip())
        assert entry["input_tokens"]  == 120
        assert entry["output_tokens"] == 80

    def test_log_feedback_writes_rating(self, tmp_path, monkeypatch):
        """log_feedback() must write a JSONL entry with the correct rating."""
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)
        ai_logger.log_feedback("suggest_tasks", "Mochi (dog)", "TASK: Feed...", "up")

        entry = json.loads((tmp_path / "ai_feedback.jsonl").read_text(encoding="utf-8").strip())
        assert entry["rating"]  == "up"
        assert entry["method"]  == "suggest_tasks"

    def test_read_stats_returns_correct_counts(self, tmp_path, monkeypatch):
        """read_stats() must count total calls, errors, and average latency correctly."""
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)

        ai_logger.log_call("suggest_tasks", "ctx", "response", 210.5, 100, 50)
        ai_logger.log_call("chat",          "ctx", None,       350.0, error=RuntimeError("fail"))

        stats = ai_logger.read_stats()
        assert stats["total"]  == 2
        assert stats["errors"] == 1
        assert stats["avg_latency_ms"] == round((210.5 + 350.0) / 2, 1)

    def test_read_stats_returns_zeros_when_no_log_file(self, tmp_path, monkeypatch):
        """read_stats() must return safe defaults when the log file doesn't exist yet."""
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)
        stats = ai_logger.read_stats()
        assert stats["total"]  == 0
        assert stats["errors"] == 0

    def test_read_feedback_stats_counts_up_and_down(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ai_logger, "_LOG_DIR", tmp_path)
        ai_logger.log_feedback("suggest_tasks", "ctx", "resp", "up")
        ai_logger.log_feedback("suggest_tasks", "ctx", "resp", "up")
        ai_logger.log_feedback("optimize_schedule", "ctx", "resp", "down")

        fb = ai_logger.read_feedback_stats()
        assert fb["up"]   == 2
        assert fb["down"] == 1
