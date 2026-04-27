import re
import streamlit as st
from pawpal_system import CareTask, PetCareStats, OwnerStats, PetPlanScheduler, Priority

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

# ── Session state initialisation ──────────────────────────────────────────────
# Every key is set ONCE on first load; Streamlit skips the block on reruns so
# the live objects survive across interactions.

if "owner" not in st.session_state:
    st.session_state.owner = None

if "pets" not in st.session_state:
    st.session_state.pets = {}

if "scheduler" not in st.session_state:
    st.session_state.scheduler = None

# Tracks whether Generate Schedule has been pressed at least once.
# Prevents the "over-budget" false-positive when tasks exist but no schedule
# has been generated yet.
if "schedule_generated" not in st.session_state:
    st.session_state.schedule_generated = False

# AI state
if "ai" not in st.session_state:
    st.session_state.ai = None           # PetCareAI instance or None

if "ai_chat_history" not in st.session_state:
    st.session_state.ai_chat_history = []  # list of {"role": ..., "content": ...}

if "ai_suggestions" not in st.session_state:
    st.session_state.ai_suggestions = {}   # pet_name -> suggestion text

if "ai_schedule_feedback" not in st.session_state:
    st.session_state.ai_schedule_feedback = ""


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
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", start_time):
        st.error("Start time must be in HH:MM 24-hour format (e.g., 08:00 or 14:30).")
    else:
        st.session_state.owner = OwnerStats(
            name=owner_name,
            available_minutes=int(available_minutes),
            preferred_start_time=start_time,
        )
        st.session_state.scheduler = PetPlanScheduler(owner=st.session_state.owner)
        st.session_state.schedule_generated = False  # reset after owner change
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
        species = st.selectbox("Species", ["dog", "cat", "rabbit", "bird", "reptile", "other"])
    with col3:
        diet = st.text_input("Diet notes (optional)", value="")

    if st.button("Add Pet"):
        if pet_name.strip() == "":
            st.error("Pet name cannot be empty.")
        elif pet_name in st.session_state.pets:
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
        if task_title.strip() == "":
            st.error("Task title cannot be empty.")
        else:
            task = CareTask(
                title=task_title.strip(),
                duration_minutes=int(task_duration),
                priority=Priority[task_priority],
                category=task_category.strip(),
                frequency=task_frequency,
            )
            st.session_state.pets[task_pet].add_task(task)
            st.success(f"Added '{task_title}' to {task_pet}.")

    # ── Daily task checklist ──────────────────────────────────────────────────
    from datetime import date
    today_label = date.today().strftime("%A, %B %d")

    has_any_tasks = any(pet.tasks for pet in st.session_state.pets.values())

    if has_any_tasks:
        st.markdown(f"### Tasks for {today_label}")

        PRIORITY_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}

        for pet in st.session_state.pets.values():
            if not pet.tasks:
                continue

            done_count  = sum(1 for t in pet.tasks if t.completed)
            total_count = len(pet.tasks)

            st.markdown(f"**{pet.name}** — {done_count}/{total_count} done")

            for task in pet.tasks:
                icon    = PRIORITY_ICON.get(task.priority.name, "⚪")
                due_str = f"  _(next: {task.due_date.strftime('%b %d')})_" if task.due_date else ""
                detail  = f"{task.duration_minutes} min · {task.category or task.frequency}"

                if task.completed:
                    st.markdown(
                        f"{icon} &nbsp; <span style='text-decoration:line-through; color:grey;'>"
                        f"**{task.title}**  {detail}</span> ✅{due_str}",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f"{icon} &nbsp; **{task.title}**  — {detail}{due_str}")

            st.divider()

        # ── Mark complete ─────────────────────────────────────────────────────
        # Collect unique titles that still have at least one incomplete instance.
        # Completing by title marks the task for each pet that owns it, using
        # the pet_name parameter to avoid accidentally completing freshly-created
        # recurrences on a second loop iteration.
        st.subheader("Mark a task complete")
        incomplete_titles = list(dict.fromkeys(
            t.title
            for pet in st.session_state.pets.values()
            for t in pet.tasks
            if not t.completed
        ))
        if incomplete_titles:
            task_to_complete = st.selectbox("Select task to mark done", incomplete_titles)
            if st.button("Mark Complete"):
                recurrences = []
                completed_count = 0

                if st.session_state.scheduler:
                    for pet in st.session_state.pets.values():
                        # Check before iterating to avoid matching a new recurrence
                        has_it = any(
                            t.title == task_to_complete and not t.completed
                            for t in pet.tasks
                        )
                        if has_it:
                            r = st.session_state.scheduler.mark_task_complete(
                                task_to_complete, pet_name=pet.name
                            )
                            completed_count += 1
                            if r:
                                recurrences.append(r)
                else:
                    # Scheduler not yet created — mark directly
                    for pet in st.session_state.pets.values():
                        for task in pet.tasks:
                            if task.title == task_to_complete and not task.completed:
                                task.mark_complete()
                                completed_count += 1

                if recurrences:
                    next_date = recurrences[0].due_date.strftime("%A, %b %d")
                    plural = f" for {completed_count} pet(s)" if completed_count > 1 else ""
                    st.success(
                        f"'{task_to_complete}' marked complete{plural}. "
                        f"Next {recurrences[0].frequency} occurrence: {next_date}."
                    )
                else:
                    plural = f" for {completed_count} pet(s)" if completed_count > 1 else ""
                    st.success(f"'{task_to_complete}' marked as complete{plural}.")
        else:
            st.success("All tasks are complete for today!")


# ── Section 4: Generate Schedule ─────────────────────────────────────────────
st.header("4. Today's Schedule")

if st.session_state.scheduler is None or not st.session_state.pets:
    st.info("Set up an owner and add pets with tasks to generate a schedule.")
else:
    if st.button("Generate Schedule"):
        st.session_state.scheduler.generate_schedule()
        st.session_state.schedule_generated = True
        st.session_state.ai_schedule_feedback = ""  # clear stale AI feedback

    if not st.session_state.schedule_generated:
        st.info("Press Generate Schedule to build today's plan.")
    else:
        schedule   = st.session_state.scheduler.schedule
        candidates = st.session_state.scheduler._get_all_candidate_tasks()
        skipped    = [t for t in candidates if t not in schedule]

        if not schedule and not skipped:
            st.info("No tasks found. Add tasks in Section 3 then generate again.")
        elif not schedule and skipped:
            st.warning(
                f"No tasks could be scheduled — all {len(skipped)} task(s) exceed your "
                f"{st.session_state.owner.available_minutes} min budget. "
                "Try increasing available time or reducing task durations."
            )
            st.caption("Tasks that did not fit:")
            for t in skipped:
                st.markdown(f"- **{t.title}** ({t.pet_name}) — {t.duration_minutes} min")
        else:
            total     = st.session_state.scheduler._total_scheduled_minutes()
            remaining = max(0, st.session_state.owner.get_availability() - total)
            st.success(f"Scheduled {len(schedule)} tasks — {total} min used, {remaining} min remaining.")

            if skipped:
                with st.expander(f"⚠️ {len(skipped)} task(s) didn't fit in your time budget"):
                    for t in skipped:
                        st.markdown(
                            f"- **{t.title}** ({t.pet_name}) — "
                            f"{t.duration_minutes} min · {t.priority.name} priority"
                        )

            conflicts = st.session_state.scheduler.detect_conflicts()
            if conflicts:
                st.error("**Scheduling conflicts detected** — two or more tasks share a time slot.")
                for warning in conflicts:
                    st.warning(f"⚠️ {warning}")
            else:
                st.success("No scheduling conflicts — all tasks have unique time slots.")

            st.subheader("Schedule (sorted by time)")
            sorted_tasks = st.session_state.scheduler.sort_by_time()
            schedule_rows = []
            for task in sorted_tasks:
                time_str = task.scheduled_time.strftime("%I:%M %p") if task.scheduled_time else "—"
                due_str  = task.due_date.strftime("%b %d") if task.due_date else "—"
                schedule_rows.append({
                    "Time":           time_str,
                    "Pet":            task.pet_name,
                    "Task":           task.title,
                    "Duration (min)": task.duration_minutes,
                    "Priority":       task.priority.name,
                    "Category":       task.category,
                    "Frequency":      task.frequency,
                    "Next Due":       due_str,
                })
            st.table(schedule_rows)

            st.subheader("Filter by pet")
            pet_names    = ["All"] + list(st.session_state.pets.keys())
            selected_pet = st.selectbox("Show tasks for:", pet_names, key="filter_pet")

            filtered = (
                st.session_state.scheduler.filter_tasks()
                if selected_pet == "All"
                else st.session_state.scheduler.filter_tasks(pet_name=selected_pet)
            )

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


# ── Section 5: AI Advisor ─────────────────────────────────────────────────────
st.header("5. AI Advisor")
st.caption(
    "Powered by Claude — specialized for pet care scheduling via a domain-tuned system prompt."
)

# ── API key input ─────────────────────────────────────────────────────────────
# Allow the user to paste a key directly in the UI without needing to restart
# the terminal. Stored in session state only — never written to disk.
import os as _os
_env_key = _os.environ.get("ANTHROPIC_API_KEY", "")

if "api_key_input" not in st.session_state:
    st.session_state.api_key_input = _env_key  # pre-fill if already in environment

typed_key = st.text_input(
    "Anthropic API key",
    value=st.session_state.api_key_input,
    type="password",
    placeholder="sk-ant-...",
    help="Get your key at console.anthropic.com. Stored in this session only, never saved to disk.",
)

# Reset the AI client whenever the key changes so it picks up the new value
if typed_key != st.session_state.api_key_input:
    st.session_state.api_key_input = typed_key
    st.session_state.ai = None          # force re-initialisation below

# Lazy-initialise the AI client and logger once a key is present
if st.session_state.ai is None and typed_key:
    try:
        from ai_advisor import PetCareAI
        import ai_logger as _ai_logger
        st.session_state.ai        = PetCareAI(api_key=typed_key)
        st.session_state.ai_logger = _ai_logger
    except ValueError as e:
        st.session_state.ai = "unavailable"
        st.error(str(e))
    except ImportError:
        st.session_state.ai = "unavailable"
        st.warning("ai_advisor module not found. Run `pip install anthropic`.")
elif st.session_state.ai is None and not typed_key:
    st.info("Paste your Anthropic API key above to enable AI features.")

ai_ready = st.session_state.ai not in (None, "unavailable")

# ── Helper: confidence badge rendering ───────────────────────────────────────
_CONF_COLOR = {"HIGH": "#22c55e", "MEDIUM": "#f97316", "LOW": "#ef4444"}

def _render_confidence_badges(text: str) -> None:
    """Render AI output, replacing CONFIDENCE: lines with coloured badges."""
    for line in text.splitlines():
        if line.startswith("CONFIDENCE:"):
            level = line.split(":", 1)[1].strip()
            color = _CONF_COLOR.get(level, "#94a3b8")
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 8px;'
                f'border-radius:4px;font-size:0.78rem;font-weight:bold;">'
                f'CONFIDENCE: {level}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(line)

# ── Helper: thumbs-up / thumbs-down buttons ───────────────────────────────────
def _feedback_buttons(key: str, method: str, context: str, response: str) -> None:
    """Render human-evaluation buttons and log the rating when clicked."""
    logger = st.session_state.get("ai_logger")
    if logger is None:
        return
    col_up, col_down, _ = st.columns([1, 1, 8])
    with col_up:
        if st.button("👍 Helpful", key=f"up_{key}"):
            logger.log_feedback(method, context, response, "up")
            st.success("Feedback saved — thanks!")
    with col_down:
        if st.button("👎 Not helpful", key=f"down_{key}"):
            logger.log_feedback(method, context, response, "down")
            st.info("Feedback saved — we'll use this to improve.")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Task Suggestions", "Schedule Optimizer", "Ask PawPal+", "Reliability Log"]
)

# ── Tab 1: Task Suggestions ───────────────────────────────────────────────────
with tab1:
    st.markdown(
        "Let the AI review your pet's profile and suggest care tasks you may have missed."
    )
    if not st.session_state.pets:
        st.info("Add at least one pet to get task suggestions.")
    elif not ai_ready:
        st.info("Add your ANTHROPIC_API_KEY to the environment to enable AI suggestions.")
    else:
        suggest_pet = st.selectbox(
            "Get suggestions for:", list(st.session_state.pets.keys()), key="suggest_pet_select"
        )
        if st.button("Suggest Tasks", key="btn_suggest"):
            pet_obj = st.session_state.pets[suggest_pet]
            with st.spinner(f"Analysing {suggest_pet}'s care profile..."):
                try:
                    result = st.session_state.ai.suggest_tasks(pet_obj)
                    st.session_state.ai_suggestions[suggest_pet] = result
                except Exception as e:
                    st.error(f"AI call failed: {e}")

        if suggest_pet in st.session_state.ai_suggestions:
            raw = st.session_state.ai_suggestions[suggest_pet]
            st.markdown("**Suggested tasks** — confidence shows how well-established each recommendation is:")
            _render_confidence_badges(raw)
            _feedback_buttons(
                key      = f"suggest_{suggest_pet}",
                method   = "suggest_tasks",
                context  = suggest_pet,
                response = raw,
            )

# ── Tab 2: Schedule Optimizer ─────────────────────────────────────────────────
with tab2:
    st.markdown(
        "After generating a schedule, ask the AI to review it and suggest improvements."
    )
    if not st.session_state.schedule_generated:
        st.info("Generate a schedule in Section 4 first.")
    elif not ai_ready:
        st.info("Add your ANTHROPIC_API_KEY to the environment to enable AI optimisation.")
    else:
        if st.button("Optimise My Schedule", key="btn_optimise"):
            with st.spinner("Reviewing your schedule..."):
                try:
                    feedback = st.session_state.ai.optimize_schedule(
                        st.session_state.owner,
                        st.session_state.scheduler.schedule,
                    )
                    st.session_state.ai_schedule_feedback = feedback
                except Exception as e:
                    st.error(f"AI call failed: {e}")

        if st.session_state.ai_schedule_feedback:
            raw = st.session_state.ai_schedule_feedback
            st.markdown("**Schedule review:**")
            st.markdown(raw)
            _feedback_buttons(
                key      = "optimise",
                method   = "optimize_schedule",
                context  = f"{st.session_state.owner.name} | {len(st.session_state.scheduler.schedule)} tasks",
                response = raw,
            )

# ── Tab 3: Q&A Chat ───────────────────────────────────────────────────────────
with tab3:
    st.markdown(
        "Ask any pet care question. The AI has full context about your registered pets."
    )
    if not ai_ready:
        st.info("Add your ANTHROPIC_API_KEY to the environment to enable the chat.")
    else:
        for turn in st.session_state.ai_chat_history:
            with st.chat_message(turn["role"]):
                st.markdown(turn["content"])

        user_input = st.chat_input("Ask a pet care question...")
        if user_input:
            st.session_state.ai_chat_history.append(
                {"role": "user", "content": user_input}
            )
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        history_for_api = st.session_state.ai_chat_history[:-1]
                        reply = st.session_state.ai.chat(
                            user_input,
                            history=history_for_api,
                            owner=st.session_state.owner,
                        )
                    except Exception as e:
                        reply = f"⚠️ AI call failed: {e}"
                st.markdown(reply)

            st.session_state.ai_chat_history.append(
                {"role": "assistant", "content": reply}
            )
            # Human-evaluation buttons on the last assistant reply
            _feedback_buttons(
                key      = f"chat_{len(st.session_state.ai_chat_history)}",
                method   = "chat",
                context  = user_input,
                response = reply,
            )

        if st.session_state.ai_chat_history:
            if st.button("Clear chat", key="btn_clear_chat"):
                st.session_state.ai_chat_history = []
                st.rerun()

# ── Tab 4: Reliability Log ────────────────────────────────────────────────────
with tab4:
    st.markdown(
        "Live stats from `logs/ai_calls.jsonl` and `logs/ai_feedback.jsonl`. "
        "Reload the tab after making AI calls to see updated numbers."
    )
    logger = st.session_state.get("ai_logger")
    if logger is None:
        st.info("AI logger not initialised — add your API key and make at least one AI call.")
    else:
        stats = logger.read_stats()
        fb    = logger.read_feedback_stats()

        # ── Call stats ────────────────────────────────────────────────────────
        st.subheader("API Call Log")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total calls",    stats["total"])
        c2.metric("Errors",         stats["errors"],
                  delta=None if stats["errors"] == 0 else f"{stats['errors']} failed",
                  delta_color="inverse")
        c3.metric("Avg latency",
                  f"{stats['avg_latency_ms']} ms" if stats["avg_latency_ms"] else "—")
        c4.metric("Total tokens",
                  stats["total_tokens"] if stats["total_tokens"] is not None else "—")

        error_rate = (
            f"{round(stats['errors'] / stats['total'] * 100, 1)} %"
            if stats["total"] > 0 else "—"
        )
        st.caption(f"Error rate: {error_rate}")

        # ── Human evaluation ──────────────────────────────────────────────────
        st.subheader("Human Evaluation")
        total_fb = fb["up"] + fb["down"]
        if total_fb == 0:
            st.info("No feedback recorded yet. Use the thumbs-up / thumbs-down buttons in the other tabs.")
        else:
            approval = round(fb["up"] / total_fb * 100, 1)
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("Helpful",     fb["up"])
            fc2.metric("Not helpful", fb["down"])
            fc3.metric("Approval",    f"{approval} %")

        # ── Raw log viewer ────────────────────────────────────────────────────
        from pathlib import Path
        log_path = Path("logs/ai_calls.jsonl")
        if log_path.exists():
            with st.expander("Raw call log (last 10 entries)"):
                lines = log_path.read_text(encoding="utf-8").splitlines()
                for line in lines[-10:]:
                    import json as _json
                    entry = _json.loads(line)
                    status = "✅" if entry.get("ok") else "❌"
                    latency = entry.get("latency_ms", "—")
                    st.caption(
                        f"{status} `{entry.get('method')}` · "
                        f"{entry.get('ts', '')[:19].replace('T', ' ')} · "
                        f"{latency} ms"
                    )
                    if entry.get("error"):
                        st.error(f"Error: {entry['error']}")
