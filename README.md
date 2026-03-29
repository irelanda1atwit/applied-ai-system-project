# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Smarter Scheduling

The `PetPlanScheduler` class was extended with four algorithmic features beyond basic priority scheduling:

**Sorting** — `sort_by_time()` returns the schedule in chronological order using `sorted()` with a lambda key that extracts each task's `"HH:MM"` string. Lexicographic comparison works correctly for 24-hour times, and tasks without a scheduled time sort to the end via a `"99:99"` sentinel.

**Filtering** — `filter_tasks(pet_name=, completed=)` returns a narrowed view of the schedule without mutating it. Filters apply sequentially with AND logic — you can isolate one pet's incomplete tasks in a single call.

**Auto-recurrence** — `mark_task_complete(title)` marks a task done and automatically creates a fresh clone for the next occurrence using Python's `timedelta`: `+1 day` for `"daily"` tasks, `+7 days` for `"weekly"` tasks. The new instance is added back to the pet so it appears in the next `generate_schedule()` call.

**Conflict detection** — `detect_conflicts()` scans the current schedule for any two tasks sharing the same time slot. It uses a `defaultdict` to bucket tasks by `"HH:MM"` key (O(n)), then returns a plain-English warning string per conflict — no exceptions raised, no schedule mutated.

## Testing PawPal+

### Run the test suite

```bash
python -m pytest tests/test_pawpal.py -v
```

### What the tests cover

The suite contains **46 tests** across 6 classes, organized by feature:

| Class | Tests | What is verified |
|---|---|---|
| `TestCareTask` | 5 | Task creation defaults, `mark_complete()` behavior, priority ordering |
| `TestPetCareStats` | 9 | Adding/removing tasks, medication tracking, feeding and walk timestamps |
| `TestOwnerStats` | 7 | Pet registration, availability, preferences, flat task aggregation |
| `TestPetPlanScheduler` | 9 | Budget enforcement, priority sorting, time assignment, zero-budget edge case |
| `TestSortByTime` | 3 | Chronological ordering, sentinel for unscheduled tasks, no schedule mutation |
| `TestRecurrence` | 4 | Daily/weekly due-date calculation via `timedelta`, clone properties, re-scheduling |
| `TestConflictDetection` | 4 | Conflict flagging, both task names in warning, clean schedule = no warnings |

Key edge cases covered: owner with 0 minutes available, pet with no tasks, task with `frequency="once"` (no recurrence), calling `detect_conflicts()` before generating a schedule, and `mark_task_complete()` with a title that doesn't exist.

### Confidence level

**4 / 5 stars**

The core scheduling logic — priority ordering, budget enforcement, recurrence, conflict detection, and sorting — is fully tested and all 46 tests pass consistently. The remaining gap is the Streamlit UI layer (`app.py`), which is not covered by unit tests. End-to-end UI behavior (user input, rendering, session state) would require integration testing to reach a 5-star confidence rating.

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.
