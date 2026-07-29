"""Deterministic event capture (spec sections 5.1, 5.3, 5.4)."""

from selfimprove import capture, config, store


def prompt_event(prompt, session="s1", turn="t1", cwd="/project"):
    return {"hook_event_name": "UserPromptSubmit", "session_id": session,
            "prompt_id": turn, "prompt": prompt, "cwd": cwd}


def failure_event(command, error, session="s1", turn="t1", cwd="/project", **extra):
    event = {"hook_event_name": "PostToolUseFailure", "session_id": session,
             "prompt_id": turn, "tool_name": "Bash",
             "tool_input": {"command": command}, "error": error, "cwd": cwd}
    event.update(extra)
    return event


def success_event(command, session="s1", turn="t1", cwd="/project"):
    return {"hook_event_name": "PostToolUse", "session_id": session,
            "prompt_id": turn, "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": cwd}


def test_a_prompt_starts_a_turn(state_root):
    record = capture.record_prompt(prompt_event("add a test"))
    assert record["session_id"] == "s1"
    assert record["turn_id"] == "t1"
    assert record["markers"] == []


def test_the_prompt_is_kept_only_for_a_correction_or_retention(state_root):
    """Section 5.1 permits the text only in that narrow case."""
    ordinary = capture.record_prompt(prompt_event("add a test"))
    assert "prompt" not in ordinary

    corrected = capture.record_prompt(
        prompt_event("no, use make test", turn="t2"))
    assert corrected["prompt"] == "no, use make test"


def test_a_kept_prompt_is_scrubbed(state_root):
    record = capture.record_prompt(
        prompt_event("remember this: key is ghp_abcdefghijklmnopqrstuvwxyz01"))
    assert "ghp_" not in record["prompt"]


def test_turn_files_are_ephemeral_and_expire(state_root):
    capture.record_prompt(prompt_event("add a test"))
    record = store.read_record(store.TURNS, "t1", subdir="s1")
    assert record["expires_at"] - record["created_at"] == config.TURN_TTL


def test_a_failure_records_only_bounded_metadata(state_root):
    """No raw output, no arguments, no environment values."""
    record = capture.record_tool_failure(failure_event(
        "pytest tests/unit --secret-flag=hunter2",
        "AssertionError: expected 1 to equal 2 in /Users/someone/private/x.py"))
    [event] = [e for e in record["events"] if e["kind"] == capture.TOOL_FAILURE]
    assert event["signature"] == "Bash:pytest"
    assert event["error_class"] == "assertion_failed"
    assert set(event) == {"kind", "ts", "tool", "signature", "error_class"}
    assert "hunter2" not in str(record)
    assert "private" not in str(record)


def test_a_user_interrupt_is_not_recorded(state_root):
    """An interrupt says nothing about whether the approach was right."""
    assert capture.record_tool_failure(
        failure_event("pytest", "interrupted", is_interrupt=True)) is None


def test_a_success_after_a_matching_failure_is_paired(state_root):
    capture.record_tool_failure(failure_event("pytest tests", "exit code 1"))
    record = capture.record_tool_success(success_event("pytest tests -x"))
    [success] = [e for e in record["events"] if e["kind"] == capture.TOOL_SUCCESS]
    assert success["after_failure"] is True
    assert success["prior_error_class"] == "nonzero_exit"
    assert success["failures_before_success"] == 1


def test_repeated_failures_are_counted_before_the_success(state_root):
    for _ in range(3):
        capture.record_tool_failure(failure_event("pytest", "exit code 1"))
    record = capture.record_tool_success(success_event("pytest"))
    [success] = [e for e in record["events"] if e["kind"] == capture.TOOL_SUCCESS]
    assert success["failures_before_success"] == 3


def test_an_unremarkable_success_is_not_recorded(state_root):
    """Most successes teach nothing and would swamp the evidence bundle."""
    capture.record_prompt(prompt_event("add a test"))
    assert capture.record_tool_success(success_event("ls")) is None


def test_a_success_of_a_different_operation_does_not_pair(state_root):
    capture.record_tool_failure(failure_event("pytest", "exit code 1"))
    assert capture.record_tool_success(success_event("npm install")) is None


def test_a_failure_is_paired_only_once(state_root):
    capture.record_tool_failure(failure_event("pytest", "exit code 1"))
    capture.record_tool_success(success_event("pytest"))
    assert capture.record_tool_success(success_event("pytest")) is None


def test_file_tool_failures_pair_on_the_same_path(state_root):
    failure = {"hook_event_name": "PostToolUseFailure", "session_id": "s1",
               "prompt_id": "t1", "tool_name": "Edit",
               "tool_input": {"file_path": "/project/src/a.py"},
               "error": "String not found", "cwd": "/project"}
    success = {"hook_event_name": "PostToolUse", "session_id": "s1",
               "prompt_id": "t1", "tool_name": "Edit",
               "tool_input": {"file_path": "/project/src/a.py"}, "cwd": "/project"}
    capture.record_tool_failure(failure)
    record = capture.record_tool_success(success)
    assert record is not None


def test_events_are_capped_per_turn(state_root, monkeypatch):
    monkeypatch.setattr(config, "MAX_EVENTS_PER_TURN", 5)
    for index in range(20):
        capture.record_tool_failure(failure_event("cmd%d" % index, "exit code 1"))
    record = store.read_record(store.TURNS, "t1", subdir="s1")
    assert len(record["events"]) == 5
    # The cap keeps the most recent activity.
    assert record["events"][-1]["signature"] == "Bash:cmd19"


def test_turns_are_isolated_by_session_and_turn(state_root):
    capture.record_tool_failure(failure_event("pytest", "x", session="a", turn="1"))
    capture.record_tool_failure(failure_event("npm", "y", session="b", turn="1"))
    first = store.read_record(store.TURNS, "1", subdir="a")
    second = store.read_record(store.TURNS, "1", subdir="b")
    assert first["events"][0]["signature"] == "Bash:pytest"
    assert second["events"][0]["signature"] == "Bash:npm"


def test_a_missing_prompt_id_falls_back_without_losing_capture(state_root):
    """Claude Code before 2.1.196 omits prompt_id."""
    event = {"hook_event_name": "PostToolUseFailure", "session_id": "s1",
             "tool_name": "Bash", "tool_input": {"command": "pytest"},
             "error": "exit code 1", "cwd": "/project"}
    record = capture.record_tool_failure(event)
    assert record is not None
    assert record["events"][0]["signature"] == "Bash:pytest"


def test_a_caller_without_a_prompt_id_finds_the_session_latest_turn(state_root):
    """A regression the smoke test caught against a real session.

    The manual review path is invoked from a skill, which knows the session but
    not the identifier Claude Code assigned to the prompt. Keying strictly on
    prompt_id meant that path loaded an empty turn and every forced review
    concluded there was nothing to learn.
    """
    capture.record_prompt(prompt_event("no, use make test", turn="prompt-abc"))
    capture.record_tool_failure(failure_event("pytest", "exit 1", turn="prompt-abc"))

    loaded = capture.load_turn({"session_id": "s1", "cwd": "/project"})
    assert loaded.get("turn_id") == "prompt-abc"
    assert loaded.get("markers") == ["correction"]
    assert len(loaded.get("events", [])) == 2


def test_a_caller_with_a_prompt_id_does_not_borrow_another_turn(state_root):
    """The fallback must not blur turns together when the id is known."""
    capture.record_prompt(prompt_event("no, use make test", turn="prompt-abc"))
    assert capture.load_turn({"session_id": "s1", "prompt_id": "prompt-xyz"}) == {}


def test_discarding_uses_the_turn_that_was_actually_loaded(state_root):
    """Otherwise the fallback would leave the prompt on disk after review."""
    capture.record_prompt(prompt_event("remember this always", turn="prompt-abc"))
    loaded = capture.load_turn({"session_id": "s1"})

    capture.discard_turn({"session_id": "s1"}, loaded)
    assert store.read_record(store.TURNS, "prompt-abc", subdir="s1",
                             allow_expired=True) is None


def test_discarding_a_turn_removes_the_file(state_root):
    capture.record_prompt(prompt_event("remember this"))
    assert capture.discard_turn(prompt_event("remember this")) is True
    assert store.read_record(store.TURNS, "t1", subdir="s1",
                             allow_expired=True) is None
