"""
ai_advisor.py — PawPal+ Specialized AI Advisor
================================================
Provides pet-care intelligence via Claude, specialized through a detailed
domain system prompt. This approach emulates a fine-tuned model: the model's
behavior is constrained to pet care scheduling expertise without retraining.

Prompt caching is applied to the large system prompt so repeated UI calls
do not re-process it on every request.

Every API call is timed and logged via ai_logger so failures and latency
spikes are always visible.
"""

import os
import time
import anthropic
import ai_logger
from pawpal_system import CareTask, PetCareStats, OwnerStats


# ── Specialized System Prompt ─────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are PawPal+, a specialized pet care scheduling assistant with deep expertise in:

## Animal Care Knowledge
- **Dogs**: feeding 1–3× per day (size/age dependent), breed-specific exercise needs (30–120 min/day),
  grooming cadence (short vs. long coat), nail trims every 3–4 weeks, dental hygiene 2–3×/week
- **Cats**: feeding 2× per day (or measured free-feed), litter scooping 1–2×/day, brushing weekly
  (daily for long-haired), enrichment 10–20 min/day, nail trims every 2 weeks
- **Small mammals** (rabbits, guinea pigs): hay always available, pellets once daily, fresh greens,
  cage cleaning every 2–3 days, socialization 30+ min/day
- **Birds**: fresh food/water daily, cage cleaning 2–3×/week, out-of-cage time 1–2 h/day,
  baths 1–2×/week depending on species
- **Reptiles**: heat lamp checks daily, feeding schedule varies by species (snakes weekly, lizards daily),
  UV lamp inspection weekly, enclosure cleaning weekly
- **Medication rules**: administer at consistent times; never skip doses; space from meals per vet instructions

## Task Suggestion Format
When suggesting tasks, always use this exact block structure, one block per task:

TASK: <descriptive task name>
DURATION: <integer minutes>
PRIORITY: HIGH | MEDIUM | LOW
CATEGORY: feeding | exercise | grooming | medication | hygiene | enrichment | vet | training
FREQUENCY: daily | weekly | as needed
CONFIDENCE: HIGH | MEDIUM | LOW
REASON: <one sentence: why this task matters for this specific pet>

CONFIDENCE key:
  HIGH   = well-established best practice for this species, backed by veterinary consensus
  MEDIUM = commonly recommended but varies by breed, age, or individual animal
  LOW    = general guidance only — verify timing and approach with your vet

## Schedule Review Format
When reviewing a schedule:
1. **Summary** (1–2 sentences): overall quality and coverage assessment
2. **Improvements** (numbered list): specific, actionable changes with timing suggestions
3. **Critical gaps**: any essential care tasks completely missing

## Q&A Format
- Answer in 2–4 sentences
- Lead with the direct answer, then briefly explain why
- Mention species-specific nuances when relevant
- Flag anything requiring veterinary consultation with: ⚠️ Consult your vet

## Hard Constraints
- Never recommend tasks that conflict with stated medications or dietary restrictions
- Always respect the owner's stated time budget; flag if schedule is unrealistic
- Prioritize animal health and welfare above scheduling convenience
- Do not diagnose medical conditions; redirect to a veterinarian when symptoms are mentioned
- If diet information is incomplete, recommend "Consult vet about optimal nutrition"
"""


# ── Context builders ──────────────────────────────────────────────────────────

def _pet_context(pet: PetCareStats) -> str:
    meds = ", ".join(pet.medications) if pet.medications else "none"
    active = [t.title for t in pet.tasks if not t.completed]
    tasks_str = ", ".join(active) if active else "none"
    return (
        f"Name: {pet.name} | Species: {pet.species}\n"
        f"Diet: {pet.diet or 'not specified'}\n"
        f"Medications: {meds}\n"
        f"Current active tasks: {tasks_str}"
    )


def _schedule_context(owner: OwnerStats, schedule: list[CareTask]) -> str:
    header = (
        f"Owner: {owner.name}\n"
        f"Available: {owner.available_minutes} min | Start: {owner.preferred_start_time}\n"
        f"Pets: {', '.join(p.name for p in owner.pets)}\n"
    )
    if not schedule:
        return header + "Schedule: not generated yet."

    rows = []
    for task in schedule:
        time_str = task.scheduled_time.strftime("%I:%M %p") if task.scheduled_time else "—"
        rows.append(
            f"  {time_str}  {task.title} ({task.pet_name}) | "
            f"{task.duration_minutes} min | {task.priority.name} | {task.category or '—'}"
        )
    return header + "Schedule:\n" + "\n".join(rows)


# ── PetCareAI ─────────────────────────────────────────────────────────────────

class PetCareAI:
    """
    Specialized pet care AI advisor.

    Uses Claude with a domain-constrained system prompt that emulates a
    fine-tuned model for pet care scheduling. The system prompt is sent
    with cache_control=ephemeral so repeated calls within a session reuse
    the cached version, cutting latency and cost.

    Every call is timed and written to logs/ai_calls.jsonl via ai_logger
    so failures, slow calls, and token usage are always observable.
    """

    MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Add it to your environment or create a .env file with ANTHROPIC_API_KEY=sk-..."
            )
        self._client = anthropic.Anthropic(api_key=key)

    def _call(
        self,
        method: str,
        context_summary: str,
        user_message: str,
        *,
        history: list[dict] | None = None,
        extra_system: str | None = None,
        max_tokens: int = 800,
    ) -> str:
        """
        Shared API call with timing and structured logging.

        Logs every attempt to logs/ai_calls.jsonl — including errors — so
        failures are never silent. Raises the original exception after logging
        so the caller and UI can handle it appropriately.
        """
        system_blocks: list[dict] = [
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if extra_system:
            system_blocks.append({"type": "text", "text": extra_system})

        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})

        t0 = time.monotonic()
        error: Exception | None = None
        response_text: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=max_tokens,
                system=system_blocks,
                messages=messages,
            )
            response_text  = response.content[0].text.strip()
            input_tokens   = getattr(response.usage, "input_tokens",  None)
            output_tokens  = getattr(response.usage, "output_tokens", None)
            return response_text

        except Exception as exc:
            error = exc
            raise

        finally:
            latency_ms = (time.monotonic() - t0) * 1000
            ai_logger.log_call(
                method          = method,
                context_summary = context_summary,
                response        = response_text,
                latency_ms      = latency_ms,
                input_tokens    = input_tokens,
                output_tokens   = output_tokens,
                error           = error,
            )

    def suggest_tasks(self, pet: PetCareStats) -> str:
        """Suggest 3–5 care tasks for a pet based on species, diet, and medications."""
        existing     = [t.title for t in pet.tasks]
        existing_str = ", ".join(existing) if existing else "none"
        ctx   = _pet_context(pet)
        prompt = (
            f"{ctx}\n\n"
            f"Tasks already in the schedule: {existing_str}\n\n"
            "Suggest 3–5 additional daily care tasks this pet needs that are NOT already "
            "covered. Use the TASK block format for each suggestion. "
            "Prioritize the most essential gaps in their care routine."
        )
        return self._call(
            method          = "suggest_tasks",
            context_summary = f"{pet.name} ({pet.species})",
            user_message    = prompt,
            max_tokens      = 700,
        )

    def optimize_schedule(self, owner: OwnerStats, schedule: list[CareTask]) -> str:
        """Review the current schedule and return actionable improvement advice."""
        ctx    = _schedule_context(owner, schedule)
        prompt = (
            f"{ctx}\n\n"
            "Review this pet care schedule using the Schedule Review Format. "
            "Focus on: task ordering, timing gaps, missing essential care, "
            "and whether the schedule is realistic within the available time budget."
        )
        return self._call(
            method          = "optimize_schedule",
            context_summary = f"{owner.name} | {len(schedule)} tasks",
            user_message    = prompt,
            max_tokens      = 600,
        )

    def chat(
        self,
        message: str,
        history: list[dict] | None = None,
        owner: OwnerStats | None = None,
    ) -> str:
        """Answer a pet care question with conversation history and optional pet context."""
        extra = None
        if owner and owner.pets:
            pet_blocks = "\n\n".join(_pet_context(p) for p in owner.pets)
            extra = f"Context — this owner's registered pets:\n{pet_blocks}"
        return self._call(
            method          = "chat",
            context_summary = (message[:80] + "...") if len(message) > 80 else message,
            user_message    = message,
            history         = history,
            extra_system    = extra,
            max_tokens      = 450,
        )
