import streamlit as st
from pawpal_system import CareTask, PetCareStats, OwnerStats, PetPlanScheduler, Priority

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

# ── Session state: the "vault" ────────────────────────────────────────────────
# st.session_state works like a dictionary that survives reruns.
# Streamlit re-executes this entire file from top to bottom on EVERY interaction
# (button click, text input, selectbox change, etc.).
#
# Without session_state, every rerun would create brand-new empty objects and
# wipe out anything the user had entered. The fix is a one-time initialization:
#
#   if "key" not in st.session_state:   ← only runs on the FIRST load
#       st.session_state.key = value    ← skipped on every subsequent rerun
#
# After that, st.session_state.key holds the live object across all reruns.

if "owner" not in st.session_state:
    # First load only — create an empty slot for the Owner object.
    # On reruns this block is skipped, so the existing Owner is preserved.
    st.session_state.owner = None

if "pets" not in st.session_state:
    # First load only — empty dict maps pet_name -> PetCareStats instance.
    st.session_state.pets = {}

if "scheduler" not in st.session_state:
    # First load only — scheduler is created once the Owner is saved.
    st.session_state.scheduler = None

# ── Section 1: Owner Setup ────────────────────────────────────────────────────
st.header("1. Owner Info")

col1, col2, col3 = st.columns(3)
with col1:
    owner_name = st.text_input("Your name", value="Jordan")
with col2:
    available_minutes = st.number_input("Available time today (min)", min_value=1, max_value=480, value=90)
with col3:
    start_time = st.text_input("Preferred start time (HH:MM)", value="08:00")

if st.button("Save Owner"):
    st.session_state.owner = OwnerStats(
        name=owner_name,
        available_minutes=int(available_minutes),
        preferred_start_time=start_time,
    )
    # Rebuild scheduler whenever owner changes
    st.session_state.scheduler = PetPlanScheduler(owner=st.session_state.owner)
    # Re-attach any existing pets to the new owner
    for pet in st.session_state.pets.values():
        st.session_state.owner.add_pet(pet)
    st.success(f"Owner saved: {owner_name} ({available_minutes} min available, starting {start_time})")

# ── Section 2: Pet Setup ──────────────────────────────────────────────────────
st.header("2. Pet Info")

if st.session_state.owner is None:
    st.info("Save an owner first before adding pets.")
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        pet_name = st.text_input("Pet name", value="Mochi")
    with col2:
        species = st.selectbox("Species", ["dog", "cat", "other"])
    with col3:
        diet = st.text_input("Diet notes (optional)", value="")

    if st.button("Add Pet"):
        if pet_name in st.session_state.pets:
            st.warning(f"{pet_name} is already added.")
        else:
            pet = PetCareStats(name=pet_name, species=species, diet=diet)
            st.session_state.pets[pet_name] = pet
            st.session_state.owner.add_pet(pet)
            st.success(f"Added {pet_name} the {species}.")

    if st.session_state.pets:
        st.write("**Registered pets:**", ", ".join(st.session_state.pets.keys()))

# ── Section 3: Task Management ────────────────────────────────────────────────
st.header("3. Tasks")

if not st.session_state.pets:
    st.info("Add at least one pet before adding tasks.")
else:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        task_pet = st.selectbox("For which pet?", list(st.session_state.pets.keys()))
    with col2:
        task_title = st.text_input("Task title", value="Morning walk")
    with col3:
        task_duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
    with col4:
        task_priority = st.selectbox("Priority", ["HIGH", "MEDIUM", "LOW"])

    col5, col6 = st.columns(2)
    with col5:
        task_category = st.text_input("Category (optional)", value="")
    with col6:
        task_frequency = st.selectbox("Frequency", ["daily", "weekly", "as needed"])

    if st.button("Add Task"):
        task = CareTask(
            title=task_title,
            duration_minutes=int(task_duration),
            priority=Priority[task_priority],
            category=task_category,
            frequency=task_frequency,
        )
        st.session_state.pets[task_pet].add_task(task)
        st.success(f"Added '{task_title}' to {task_pet}.")

    # Display all current tasks per pet
    all_rows = []
    for pet in st.session_state.pets.values():
        for task in pet.tasks:
            all_rows.append({
                "Pet": pet.name,
                "Task": task.title,
                "Duration (min)": task.duration_minutes,
                "Priority": task.priority.name,
                "Category": task.category,
                "Frequency": task.frequency,
                "Done": "Yes" if task.completed else "No",
            })

    if all_rows:
        st.write("**All tasks:**")
        st.table(all_rows)

        # Mark complete — routes through scheduler so recurrence fires automatically
        st.subheader("Mark a task complete")
        all_task_titles = [r["Task"] for r in all_rows if r["Done"] == "No"]
        if all_task_titles:
            task_to_complete = st.selectbox("Select task to mark done", all_task_titles)
            if st.button("Mark Complete"):
                if st.session_state.scheduler:
                    recurrence = st.session_state.scheduler.mark_task_complete(task_to_complete)
                    if recurrence:
                        st.success(
                            f"'{task_to_complete}' marked complete. "
                            f"Next {recurrence.frequency} occurrence scheduled for "
                            f"{recurrence.due_date.strftime('%A, %b %d')}."
                        )
                    else:
                        st.success(f"'{task_to_complete}' marked as complete.")
                else:
                    # Fallback if scheduler not yet built
                    for pet in st.session_state.pets.values():
                        for task in pet.tasks:
                            if task.title == task_to_complete and not task.completed:
                                task.mark_complete()
                    st.success(f"'{task_to_complete}' marked as complete.")
        else:
            st.info("All tasks are complete!")

# ── Section 4: Generate Schedule ─────────────────────────────────────────────
st.header("4. Today's Schedule")

if st.session_state.scheduler is None or not st.session_state.pets:
    st.info("Set up an owner and add pets with tasks to generate a schedule.")
else:
    if st.button("Generate Schedule"):
        schedule = st.session_state.scheduler.generate_schedule()

        if not schedule:
            st.warning("No tasks could be scheduled. Check your time budget or add more tasks.")
        else:
            total     = st.session_state.scheduler._total_scheduled_minutes()
            remaining = st.session_state.owner.get_availability() - total
            st.success(f"Scheduled {len(schedule)} tasks — {total} min used, {remaining} min remaining.")

            # ── Conflict warnings ─────────────────────────────────────────
            conflicts = st.session_state.scheduler.detect_conflicts()
            if conflicts:
                st.error("**Scheduling conflicts detected** — two or more tasks are assigned to the same time slot. Review and adjust durations or priorities.")
                for warning in conflicts:
                    # Parse out the time and task names for a friendlier message
                    st.warning(f"⚠️ {warning}")
            else:
                st.success("No scheduling conflicts — all tasks have unique time slots.")

            # ── Sorted schedule table ─────────────────────────────────────
            st.subheader("Schedule (sorted by time)")
            sorted_tasks = st.session_state.scheduler.sort_by_time()
            schedule_rows = []
            for task in sorted_tasks:
                time_str = task.scheduled_time.strftime("%I:%M %p") if task.scheduled_time else "—"
                due_str  = task.due_date.strftime("%b %d") if task.due_date else "—"
                schedule_rows.append({
                    "Time":          time_str,
                    "Pet":           task.pet_name,
                    "Task":          task.title,
                    "Duration (min)": task.duration_minutes,
                    "Priority":      task.priority.name,
                    "Category":      task.category,
                    "Frequency":     task.frequency,
                    "Next Due":      due_str,
                })
            st.table(schedule_rows)

            # ── Filter by pet ─────────────────────────────────────────────
            st.subheader("Filter by pet")
            pet_names = ["All"] + list(st.session_state.pets.keys())
            selected_pet = st.selectbox("Show tasks for:", pet_names, key="filter_pet")

            if selected_pet == "All":
                filtered = st.session_state.scheduler.filter_tasks()
            else:
                filtered = st.session_state.scheduler.filter_tasks(pet_name=selected_pet)

            if filtered:
                filter_rows = []
                for task in filtered:
                    time_str = task.scheduled_time.strftime("%I:%M %p") if task.scheduled_time else "—"
                    filter_rows.append({
                        "Time":           time_str,
                        "Task":           task.title,
                        "Duration (min)": task.duration_minutes,
                        "Priority":       task.priority.name,
                        "Category":       task.category,
                    })
                st.table(filter_rows)
            else:
                st.info(f"No scheduled tasks found for {selected_pet}.")
