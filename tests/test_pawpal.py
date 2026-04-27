"""
tests/test_pawpal.py — Pytest suite for PawPal+ logic layer
============================================================
Run with:
    pytest tests/test_pawpal.py -v
"""

import pytest
from datetime import datetime, timedelta
from pawpal_system import CareTask, PetCareStats, OwnerStats, PetPlanScheduler, Priority


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def basic_task():
    return CareTask(title="Morning walk", duration_minutes=20, priority=Priority.HIGH, category="exercise")


@pytest.fixture
def short_task():
    return CareTask(title="Feed pet", duration_minutes=5, priority=Priority.LOW, category="feeding")


@pytest.fixture
def dog():
    return PetCareStats(name="Mochi", species="dog", diet="grain-free")


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
def scheduler(owner):
    return PetPlanScheduler(owner=owner)


# ── CareTask Tests ────────────────────────────────────────────────────────────

class TestCareTask:

    def test_task_completion_changes_status(self, basic_task):
        assert basic_task.completed is False
        basic_task.mark_complete()
        assert basic_task.completed is True

    def test_mark_complete_is_idempotent(self, basic_task):
        basic_task.mark_complete()
        basic_task.mark_complete()
        assert basic_task.completed is True

    def test_task_default_values(self, basic_task):
        assert basic_task.scheduled_time is None
        assert basic_task.pet_name == ""
        assert basic_task.frequency == "daily"
        assert basic_task.completed is False

    def test_priority_ordering(self):
        assert Priority.HIGH.value > Priority.MEDIUM.value > Priority.LOW.value

    def test_task_stores_duration(self):
        task = CareTask(title="Groom", duration_minutes=45, priority=Priority.MEDIUM)
        assert task.duration_minutes == 45

    def test_task_category_defaults_to_empty_string(self):
        """category should be empty string when not provided, not None."""
        task = CareTask(title="Walk", duration_minutes=10, priority=Priority.LOW)
        assert task.category == ""

    def test_task_pet_name_defaults_to_empty_string(self):
        """pet_name should be empty string before the task is attached to a pet."""
        task = CareTask(title="Walk", duration_minutes=10, priority=Priority.HIGH)
        assert task.pet_name == ""

    def test_task_due_date_defaults_to_none(self):
        task = CareTask(title="Walk", duration_minutes=10, priority=Priority.HIGH)
        assert task.due_date is None

    def test_task_with_zero_duration_is_valid(self):
        """Zero-duration tasks are technically valid objects; the scheduler skips
        them only if the budget is also 0 (0 <= 0 is True)."""
        task = CareTask(title="Quick check", duration_minutes=0, priority=Priority.LOW)
        assert task.duration_minutes == 0

    def test_task_frequency_values(self):
        """Verify that all expected frequency strings round-trip correctly."""
        for freq in ("daily", "weekly", "as needed", "once"):
            t = CareTask(title="T", duration_minutes=1, priority=Priority.LOW, frequency=freq)
            assert t.frequency == freq


# ── PetCareStats Tests ────────────────────────────────────────────────────────

class TestPetCareStats:

    def test_add_task_increases_count(self, dog, basic_task):
        before = len(dog.tasks)
        dog.add_task(basic_task)
        assert len(dog.tasks) == before + 1

    def test_add_multiple_tasks_increases_count(self, dog, basic_task, short_task):
        dog.add_task(basic_task)
        dog.add_task(short_task)
        assert len(dog.tasks) == 2

    def test_add_task_stamps_pet_name(self, dog, basic_task):
        dog.add_task(basic_task)
        assert basic_task.pet_name == "Mochi"

    def test_remove_task_decreases_count(self, dog, basic_task):
        dog.add_task(basic_task)
        assert len(dog.tasks) == 1
        dog.remove_task("Morning walk")
        assert len(dog.tasks) == 0

    def test_remove_nonexistent_task_does_nothing(self, dog):
        dog.remove_task("Ghost task")
        assert len(dog.tasks) == 0

    def test_add_medication(self, dog):
        dog.add_medication("Apoquel 16mg")
        assert "Apoquel 16mg" in dog.medications

    def test_add_multiple_medications(self, dog):
        dog.add_medication("Apoquel 16mg")
        dog.add_medication("Probiotic")
        assert len(dog.medications) == 2

    def test_update_last_fed(self, dog):
        assert dog.last_fed is None
        before = datetime.now()
        dog.update_last_fed()
        assert dog.last_fed is not None
        assert dog.last_fed >= before

    def test_update_last_walked(self, dog):
        assert dog.last_walked is None
        before = datetime.now()
        dog.update_last_walked()
        assert dog.last_walked is not None
        assert dog.last_walked >= before

    def test_remove_task_removes_all_with_same_title(self, dog):
        """remove_task() uses a list comprehension so every task sharing the title
        is removed, not just the first match."""
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        assert len(dog.tasks) == 2
        dog.remove_task("Feed")
        assert len(dog.tasks) == 0

    def test_tasks_list_not_shared_between_instances(self):
        """Each PetCareStats must get its own tasks list from default_factory=list.
        A common Python bug is using a mutable default argument, which is shared."""
        pet_a = PetCareStats(name="A", species="dog")
        pet_b = PetCareStats(name="B", species="cat")
        pet_a.add_task(CareTask(title="Walk", duration_minutes=10, priority=Priority.HIGH))
        assert len(pet_b.tasks) == 0

    def test_medications_list_not_shared_between_instances(self):
        """Each pet must own its own medications list."""
        pet_a = PetCareStats(name="A", species="dog")
        pet_b = PetCareStats(name="B", species="cat")
        pet_a.add_medication("Apoquel")
        assert len(pet_b.medications) == 0

    def test_update_last_fed_overwrites_previous_timestamp(self, dog):
        """Calling update_last_fed() twice should move the timestamp forward."""
        dog.update_last_fed()
        first = dog.last_fed
        dog.update_last_fed()
        assert dog.last_fed >= first

    def test_add_task_to_one_pet_does_not_affect_another(self, dog, cat, basic_task):
        dog.add_task(basic_task)
        assert len(cat.tasks) == 0


# ── OwnerStats Tests ──────────────────────────────────────────────────────────

class TestOwnerStats:

    def test_add_pet_increases_count(self, dog):
        o = OwnerStats(name="Sam", available_minutes=60)
        assert len(o.pets) == 0
        o.add_pet(dog)
        assert len(o.pets) == 1

    def test_get_availability_returns_minutes(self):
        o = OwnerStats(name="Sam", available_minutes=45)
        assert o.get_availability() == 45

    def test_set_preferences(self):
        o = OwnerStats(name="Sam", available_minutes=60)
        o.set_preferences(["no early walks", "short sessions"])
        assert o.preferences == ["no early walks", "short sessions"]

    def test_set_preferences_replaces_existing(self):
        o = OwnerStats(name="Sam", available_minutes=60)
        o.set_preferences(["first pref"])
        o.set_preferences(["updated pref"])
        assert o.preferences == ["updated pref"]

    def test_get_all_tasks_collects_across_pets(self, owner, dog, cat, basic_task, short_task):
        dog.add_task(basic_task)
        cat.add_task(short_task)
        all_tasks = owner.get_all_tasks()
        assert len(all_tasks) == 2

    def test_get_all_tasks_excludes_completed(self, owner, dog, basic_task):
        dog.add_task(basic_task)
        basic_task.mark_complete()
        all_tasks = owner.get_all_tasks()
        assert len(all_tasks) == 0

    def test_get_all_tasks_empty_with_no_pets(self):
        o = OwnerStats(name="Empty", available_minutes=60)
        assert o.get_all_tasks() == []

    def test_default_preferred_start_time(self):
        """OwnerStats should default to '08:00' when start_time is omitted."""
        o = OwnerStats(name="Sam", available_minutes=60)
        assert o.preferred_start_time == "08:00"

    def test_pets_list_not_shared_between_instances(self):
        """Each OwnerStats must own its own pets list."""
        o1 = OwnerStats(name="Alice", available_minutes=60)
        o2 = OwnerStats(name="Bob",   available_minutes=60)
        o1.add_pet(PetCareStats(name="Rex", species="dog"))
        assert len(o2.pets) == 0

    def test_get_all_tasks_counts_from_all_pets(self):
        """With three pets each having one task, get_all_tasks must return 3 items."""
        owner = OwnerStats(name="Multi", available_minutes=120)
        for i in range(3):
            pet = PetCareStats(name=f"Pet{i}", species="dog")
            pet.add_task(CareTask(title=f"Task{i}", duration_minutes=10, priority=Priority.MEDIUM))
            owner.add_pet(pet)
        assert len(owner.get_all_tasks()) == 3


# ── PetPlanScheduler Tests ────────────────────────────────────────────────────

class TestPetPlanScheduler:

    def test_generate_schedule_respects_budget(self, owner, dog):
        dog.add_task(CareTask(title="Task A", duration_minutes=50, priority=Priority.HIGH))
        dog.add_task(CareTask(title="Task B", duration_minutes=50, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        assert scheduler._total_scheduled_minutes() <= owner.available_minutes

    def test_generate_schedule_high_priority_first(self, owner, dog):
        dog.add_task(CareTask(title="Low task",  duration_minutes=10, priority=Priority.LOW))
        dog.add_task(CareTask(title="High task", duration_minutes=10, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        titles = [t.title for t in schedule]
        assert titles.index("High task") < titles.index("Low task")

    def test_generate_schedule_assigns_scheduled_time(self, owner, dog, basic_task):
        dog.add_task(basic_task)
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        for task in schedule:
            assert task.scheduled_time is not None

    def test_generate_schedule_excludes_completed_tasks(self, owner, dog, basic_task):
        basic_task.mark_complete()
        dog.add_task(basic_task)
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        assert basic_task not in schedule

    def test_generate_schedule_zero_budget(self, dog):
        broke_owner = OwnerStats(name="Tired", available_minutes=0)
        broke_owner.add_pet(dog)
        dog.add_task(CareTask(title="Walk", duration_minutes=20, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=broke_owner)
        schedule = scheduler.generate_schedule()
        assert schedule == []

    def test_generate_schedule_no_tasks(self, owner):
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        assert schedule == []

    def test_total_scheduled_minutes_is_accurate(self, owner, dog):
        dog.add_task(CareTask(title="Task A", duration_minutes=15, priority=Priority.HIGH))
        dog.add_task(CareTask(title="Task B", duration_minutes=20, priority=Priority.MEDIUM))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        assert scheduler._total_scheduled_minutes() == 35

    def test_remove_task_from_scheduler(self, owner, dog):
        task = CareTask(title="Groom", duration_minutes=15, priority=Priority.LOW)
        dog.add_task(task)
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.remove_task("Groom")
        assert all(t.title != "Groom" for t in dog.tasks)

    def test_explain_plan_before_schedule(self, scheduler):
        result = scheduler.explain_plan()
        assert len(result) == 1
        assert "generate_schedule" in result[0]

    def test_explain_plan_returns_one_entry_per_task(self, owner, dog):
        dog.add_task(CareTask(title="Walk", duration_minutes=10, priority=Priority.HIGH))
        dog.add_task(CareTask(title="Feed", duration_minutes=5,  priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        explanations = scheduler.explain_plan()
        assert len(explanations) == 3  # 2 tasks + 1 summary line

    def test_schedule_rebuilds_after_completion(self, owner, dog):
        task = CareTask(title="Walk", duration_minutes=20, priority=Priority.HIGH)
        dog.add_task(task)
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        assert task in scheduler.schedule

        task.mark_complete()
        scheduler.generate_schedule()
        assert task not in scheduler.schedule

    def test_shorter_tasks_used_as_tiebreak(self, owner, dog):
        dog.add_task(CareTask(title="Long",  duration_minutes=30, priority=Priority.MEDIUM))
        dog.add_task(CareTask(title="Short", duration_minutes=5,  priority=Priority.MEDIUM))
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        titles = [t.title for t in schedule]
        assert titles.index("Short") < titles.index("Long")

    def test_mark_task_complete_nonexistent_title_returns_none(self, owner):
        scheduler = PetPlanScheduler(owner=owner)
        result = scheduler.mark_task_complete("Ghost Task")
        assert result is None

    def test_mark_task_complete_once_frequency_does_not_recur(self, owner, dog):
        task = CareTask(title="Vet visit", duration_minutes=60, priority=Priority.HIGH, frequency="once")
        dog.add_task(task)
        scheduler = PetPlanScheduler(owner=owner)

        result = scheduler.mark_task_complete("Vet visit")

        assert task.completed is True
        assert result is None
        assert len(dog.tasks) == 1
        assert dog.tasks[0].completed is True

    # ── New: boundary & schedule regeneration ────────────────────────────────

    def test_generate_schedule_task_exactly_at_budget(self, dog):
        """A task whose duration equals the budget exactly must be scheduled."""
        tight_owner = OwnerStats(name="Tight", available_minutes=30)
        tight_owner.add_pet(dog)
        dog.add_task(CareTask(title="Exact fit", duration_minutes=30, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=tight_owner)
        schedule = scheduler.generate_schedule()
        assert len(schedule) == 1
        assert schedule[0].title == "Exact fit"

    def test_generate_schedule_fresh_on_second_call(self, owner, dog):
        """Calling generate_schedule() twice must not duplicate tasks in the
        schedule — the schedule list is reset at the start of each call."""
        dog.add_task(CareTask(title="Walk", duration_minutes=20, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        scheduler.generate_schedule()
        assert len(scheduler.schedule) == 1

    def test_generate_schedule_respects_preferred_start_time(self, dog):
        """The first scheduled task must begin at the owner's preferred start time."""
        owner = OwnerStats(name="Pam", available_minutes=60, preferred_start_time="10:30")
        owner.add_pet(dog)
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        first = scheduler.schedule[0]
        assert first.scheduled_time.hour == 10
        assert first.scheduled_time.minute == 30

    def test_generate_schedule_midnight_start_time(self, dog):
        """'00:00' is a valid start time and must not crash or fall back."""
        owner = OwnerStats(name="Night owl", available_minutes=30, preferred_start_time="00:00")
        owner.add_pet(dog)
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        assert scheduler.schedule[0].scheduled_time.hour == 0
        assert scheduler.schedule[0].scheduled_time.minute == 0

    def test_generate_schedule_malformed_start_time_does_not_crash(self, dog):
        """A non-HH:MM start time must fall back to 08:00 instead of raising."""
        owner = OwnerStats(name="Typo", available_minutes=30, preferred_start_time="abc")
        owner.add_pet(dog)
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        assert len(schedule) == 1
        assert schedule[0].scheduled_time.hour == 8
        assert schedule[0].scheduled_time.minute == 0

    def test_generate_schedule_out_of_range_time_falls_back(self, dog):
        """Times like '25:00' are syntactically valid splits but semantically
        invalid — the scheduler must fall back rather than crashing on replace()."""
        owner = OwnerStats(name="Typo2", available_minutes=30, preferred_start_time="25:00")
        owner.add_pet(dog)
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        assert len(schedule) == 1
        assert schedule[0].scheduled_time.hour == 8

    def test_tasks_from_multiple_pets_all_scheduled(self, owner, dog, cat):
        """Tasks belonging to different pets must all appear in a combined schedule."""
        dog.add_task(CareTask(title="Walk Mochi",    duration_minutes=20, priority=Priority.HIGH))
        cat.add_task(CareTask(title="Feed Whiskers", duration_minutes=5,  priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        schedule = scheduler.generate_schedule()
        titles = [t.title for t in schedule]
        assert "Walk Mochi"    in titles
        assert "Feed Whiskers" in titles

    # ── New: extra tasks (added directly to scheduler) ────────────────────────

    def test_extra_task_added_directly_to_scheduler_is_scheduled(self, owner):
        """Tasks added via scheduler.add_task() (not via a pet) must appear
        in the generated schedule alongside pet tasks."""
        scheduler = PetPlanScheduler(owner=owner)
        extra = CareTask(title="Vet call", duration_minutes=10, priority=Priority.HIGH)
        scheduler.add_task(extra)
        schedule = scheduler.generate_schedule()
        assert extra in schedule

    def test_remove_task_also_removes_from_active_schedule(self, owner, dog):
        """remove_task() must clean the task out of self.schedule, not only the
        pet's task list — otherwise a stale entry lingers after the next render."""
        task = CareTask(title="Bath", duration_minutes=15, priority=Priority.HIGH)
        dog.add_task(task)
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        assert task in scheduler.schedule

        scheduler.remove_task("Bath")
        assert task not in scheduler.schedule

    # ── New: filter_tasks edge cases ─────────────────────────────────────────

    def test_filter_tasks_combined_pet_and_completed_false(self, owner, dog, cat):
        """filter_tasks with both pet_name and completed=False must apply AND logic."""
        dog.add_task(CareTask(title="Walk",    duration_minutes=20, priority=Priority.HIGH))
        dog.add_task(CareTask(title="Groom",   duration_minutes=15, priority=Priority.LOW))
        cat.add_task(CareTask(title="Play",    duration_minutes=10, priority=Priority.MEDIUM))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        # Mark Mochi's Walk complete
        for t in scheduler.schedule:
            if t.title == "Walk":
                t.mark_complete()
                break

        results = scheduler.filter_tasks(pet_name="Mochi", completed=False)
        assert all(t.pet_name == "Mochi" for t in results)
        assert all(not t.completed for t in results)

    def test_filter_tasks_no_match_returns_empty_list(self, owner, dog):
        """Filtering for a pet that has no scheduled tasks must return [] not raise."""
        dog.add_task(CareTask(title="Walk", duration_minutes=20, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        result = scheduler.filter_tasks(pet_name="Nonexistent")
        assert result == []

    def test_filter_tasks_before_generate_returns_empty(self, owner):
        """Calling filter_tasks() before generate_schedule() must return []."""
        scheduler = PetPlanScheduler(owner=owner)
        assert scheduler.filter_tasks() == []
        assert scheduler.filter_tasks(pet_name="Mochi") == []

    # ── New: explain_plan edge cases ─────────────────────────────────────────

    def test_explain_plan_remaining_minutes_never_negative(self, dog):
        """If the budget is exactly consumed, remaining must show 0 not a negative
        number — guards the max(0, ...) fix in explain_plan()."""
        owner = OwnerStats(name="Full", available_minutes=15)
        owner.add_pet(dog)
        dog.add_task(CareTask(title="Walk", duration_minutes=15, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        summary = scheduler.explain_plan()[-1]
        assert "Remaining available: 0 min" in summary

    # ── New: mark_task_complete with pet_name ─────────────────────────────────

    def test_mark_task_complete_with_pet_name_targets_specific_pet(self, owner, dog, cat):
        """Passing pet_name must complete only that pet's task and leave the
        other pet's identically-named task untouched."""
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        cat.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)

        scheduler.mark_task_complete("Feed", pet_name="Mochi")

        mochi_task   = next(t for t in dog.tasks if t.title == "Feed" and t.completed)
        whiskers_feed = [t for t in cat.tasks if t.title == "Feed" and not t.completed]

        assert mochi_task is not None
        assert len(whiskers_feed) == 1  # Whiskers' task still incomplete

    def test_mark_task_complete_with_pet_name_does_not_complete_wrong_pet(self, owner, dog, cat):
        """After completing one pet's task by name, the other pet's same-titled
        task must remain incomplete — no accidental cross-pet completion."""
        dog.add_task(CareTask(title="Morning feed", duration_minutes=5, priority=Priority.HIGH))
        cat.add_task(CareTask(title="Morning feed", duration_minutes=5, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)

        scheduler.mark_task_complete("Morning feed", pet_name="Whiskers")

        cat_task = next(t for t in cat.tasks if t.title == "Morning feed")
        dog_task = next(t for t in dog.tasks if t.title == "Morning feed")

        assert cat_task.completed is True
        assert dog_task.completed is False

    def test_mark_task_complete_already_completed_returns_none(self, owner, dog):
        """If every task with the given title is already complete, the method
        must return None rather than raising or creating a phantom recurrence."""
        task = CareTask(title="Walk", duration_minutes=20, priority=Priority.HIGH, frequency="daily")
        dog.add_task(task)
        task.mark_complete()
        scheduler = PetPlanScheduler(owner=owner)

        result = scheduler.mark_task_complete("Walk")
        assert result is None

    def test_mark_task_complete_as_needed_frequency_no_recurrence(self, owner, dog):
        """'as needed' tasks must be marked done but must not create a recurrence."""
        task = CareTask(title="Vet checkup", duration_minutes=60,
                        priority=Priority.HIGH, frequency="as needed")
        dog.add_task(task)
        scheduler = PetPlanScheduler(owner=owner)

        result = scheduler.mark_task_complete("Vet checkup")

        assert task.completed is True
        assert result is None
        # Only the original task exists — no clone
        vet_tasks = [t for t in dog.tasks if t.title == "Vet checkup"]
        assert len(vet_tasks) == 1


# ── Sorting Tests ─────────────────────────────────────────────────────────────

class TestSortByTime:

    def test_sort_by_time_returns_chronological_order(self, owner, dog):
        dog.add_task(CareTask(title="First",  duration_minutes=2,  priority=Priority.HIGH))
        dog.add_task(CareTask(title="Second", duration_minutes=5,  priority=Priority.HIGH))
        dog.add_task(CareTask(title="Third",  duration_minutes=10, priority=Priority.LOW))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        sorted_tasks = scheduler.sort_by_time()
        times = [t.scheduled_time for t in sorted_tasks]
        assert all(times[i] <= times[i + 1] for i in range(len(times) - 1))

    def test_sort_by_time_does_not_mutate_schedule(self, owner, dog):
        dog.add_task(CareTask(title="Walk", duration_minutes=20, priority=Priority.LOW))
        dog.add_task(CareTask(title="Feed", duration_minutes=5,  priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        original_order = [t.title for t in scheduler.schedule]
        scheduler.sort_by_time()

        assert [t.title for t in scheduler.schedule] == original_order

    def test_sort_by_time_tasks_without_scheduled_time_go_last(self, owner, dog):
        dog.add_task(CareTask(title="Timed", duration_minutes=5, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        unscheduled = CareTask(title="No Time", duration_minutes=5, priority=Priority.LOW)
        scheduler.schedule.append(unscheduled)

        sorted_tasks = scheduler.sort_by_time()
        assert sorted_tasks[-1].title == "No Time"

    def test_sort_by_time_single_task_returns_list_of_one(self, owner, dog):
        """sort_by_time() on a one-task schedule must return a list with that task."""
        dog.add_task(CareTask(title="Solo", duration_minutes=10, priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        result = scheduler.sort_by_time()
        assert len(result) == 1
        assert result[0].title == "Solo"

    def test_sort_by_time_empty_schedule_returns_empty_list(self, owner):
        """sort_by_time() on an empty schedule must return [] without raising."""
        scheduler = PetPlanScheduler(owner=owner)
        assert scheduler.sort_by_time() == []


# ── Recurrence Tests ──────────────────────────────────────────────────────────

class TestRecurrence:

    def test_daily_task_creates_recurrence_due_tomorrow(self, owner, dog):
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH, frequency="daily"))
        scheduler = PetPlanScheduler(owner=owner)

        tomorrow = (datetime.today() + timedelta(days=1)).date()
        recurrence = scheduler.mark_task_complete("Feed")

        assert recurrence is not None
        assert recurrence.due_date.date() == tomorrow

    def test_weekly_task_creates_recurrence_due_next_week(self, owner, dog):
        dog.add_task(CareTask(title="Bath", duration_minutes=20, priority=Priority.MEDIUM, frequency="weekly"))
        scheduler = PetPlanScheduler(owner=owner)

        next_week = (datetime.today() + timedelta(days=7)).date()
        recurrence = scheduler.mark_task_complete("Bath")

        assert recurrence is not None
        assert recurrence.due_date.date() == next_week

    def test_recurrence_appears_in_next_generate_schedule(self, owner, dog):
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH, frequency="daily"))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        scheduler.mark_task_complete("Feed")
        new_schedule = scheduler.generate_schedule()

        titles = [t.title for t in new_schedule]
        assert "Feed" in titles

    def test_recurrence_inherits_original_task_properties(self, owner, dog):
        original = CareTask(title="Walk", duration_minutes=30, priority=Priority.HIGH,
                            category="exercise", frequency="daily")
        dog.add_task(original)
        scheduler = PetPlanScheduler(owner=owner)

        recurrence = scheduler.mark_task_complete("Walk")

        assert recurrence.title             == original.title
        assert recurrence.duration_minutes  == original.duration_minutes
        assert recurrence.priority          == original.priority
        assert recurrence.category          == original.category
        assert recurrence.frequency         == original.frequency
        assert recurrence.completed         is False

    def test_recurrence_is_not_completed(self, owner, dog):
        """The cloned recurrence task must start as incomplete."""
        dog.add_task(CareTask(title="Feed", duration_minutes=5, priority=Priority.HIGH, frequency="daily"))
        scheduler = PetPlanScheduler(owner=owner)
        recurrence = scheduler.mark_task_complete("Feed")
        assert recurrence.completed is False

    def test_original_task_is_completed_after_mark(self, owner, dog):
        """The original task must be marked complete, not the recurrence."""
        original = CareTask(title="Walk", duration_minutes=20, priority=Priority.HIGH, frequency="daily")
        dog.add_task(original)
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.mark_task_complete("Walk")
        assert original.completed is True

    def test_recurrence_pet_name_is_stamped(self, owner, dog):
        """The recurrence returned by mark_task_complete() must have pet_name set
        because add_task() on the host pet stamps it immediately."""
        dog.add_task(CareTask(title="Feed", duration_minutes=5,
                              priority=Priority.HIGH, frequency="daily"))
        scheduler = PetPlanScheduler(owner=owner)
        recurrence = scheduler.mark_task_complete("Feed")
        assert recurrence.pet_name == "Mochi"


# ── Conflict Detection Tests ──────────────────────────────────────────────────

class TestConflictDetection:

    def test_detect_conflicts_flags_same_time_slot(self, owner, dog, cat):
        clash_time = datetime.today().replace(hour=9, minute=0, second=0, microsecond=0)

        task_a = CareTask(title="Walk Mochi",    duration_minutes=20, priority=Priority.HIGH)
        task_b = CareTask(title="Feed Whiskers", duration_minutes=5,  priority=Priority.HIGH)
        dog.add_task(task_a)
        cat.add_task(task_b)

        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        task_a.scheduled_time = clash_time
        task_b.scheduled_time = clash_time

        warnings = scheduler.detect_conflicts()
        assert len(warnings) == 1
        assert "09:00" in warnings[0]

    def test_detect_conflicts_returns_empty_for_clean_schedule(self, owner, dog):
        dog.add_task(CareTask(title="Walk", duration_minutes=20, priority=Priority.HIGH))
        dog.add_task(CareTask(title="Feed", duration_minutes=5,  priority=Priority.HIGH))
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()
        assert scheduler.detect_conflicts() == []

    def test_detect_conflicts_before_generate_returns_empty(self, owner):
        scheduler = PetPlanScheduler(owner=owner)
        assert scheduler.detect_conflicts() == []

    def test_detect_conflicts_reports_both_task_names(self, owner, dog, cat):
        clash_time = datetime.today().replace(hour=10, minute=0, second=0, microsecond=0)

        task_a = CareTask(title="Groom Mochi",  duration_minutes=15, priority=Priority.MEDIUM)
        task_b = CareTask(title="Clean Litter", duration_minutes=10, priority=Priority.MEDIUM)
        dog.add_task(task_a)
        cat.add_task(task_b)

        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        task_a.scheduled_time = clash_time
        task_b.scheduled_time = clash_time

        warning = scheduler.detect_conflicts()[0]
        assert "Groom Mochi"  in warning
        assert "Clean Litter" in warning

    def test_detect_conflicts_three_tasks_same_slot(self, owner, dog, cat):
        """Three tasks forced into the same slot must all appear in a single
        warning string — the bucket holds all three, not just the first two."""
        clash_time = datetime.today().replace(hour=11, minute=0, second=0, microsecond=0)

        task_a = CareTask(title="Alpha", duration_minutes=5, priority=Priority.HIGH)
        task_b = CareTask(title="Beta",  duration_minutes=5, priority=Priority.HIGH)
        task_c = CareTask(title="Gamma", duration_minutes=5, priority=Priority.MEDIUM)
        dog.add_task(task_a)
        cat.add_task(task_b)

        # Add third task directly to the scheduler pool
        scheduler = PetPlanScheduler(owner=owner)
        scheduler.add_task(task_c)
        scheduler.generate_schedule()

        task_a.scheduled_time = clash_time
        task_b.scheduled_time = clash_time
        task_c.scheduled_time = clash_time

        warnings = scheduler.detect_conflicts()
        assert len(warnings) == 1
        assert "Alpha" in warnings[0]
        assert "Beta"  in warnings[0]
        assert "Gamma" in warnings[0]

    def test_detect_conflicts_multiple_distinct_slots(self, owner, dog, cat):
        """Two separate conflicting slots must each produce their own warning."""
        slot_a = datetime.today().replace(hour=9,  minute=0, second=0, microsecond=0)
        slot_b = datetime.today().replace(hour=10, minute=0, second=0, microsecond=0)

        t1 = CareTask(title="T1", duration_minutes=5, priority=Priority.HIGH)
        t2 = CareTask(title="T2", duration_minutes=5, priority=Priority.HIGH)
        t3 = CareTask(title="T3", duration_minutes=5, priority=Priority.MEDIUM)
        t4 = CareTask(title="T4", duration_minutes=5, priority=Priority.MEDIUM)
        dog.add_task(t1)
        dog.add_task(t2)
        cat.add_task(t3)
        cat.add_task(t4)

        scheduler = PetPlanScheduler(owner=owner)
        scheduler.generate_schedule()

        t1.scheduled_time = slot_a
        t2.scheduled_time = slot_a
        t3.scheduled_time = slot_b
        t4.scheduled_time = slot_b

        warnings = scheduler.detect_conflicts()
        assert len(warnings) == 2
