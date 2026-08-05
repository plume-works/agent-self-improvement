"""Capture driven by real hook payloads through ``scripts/si``.

Spec section 14 requires a JSON fixture per supported event. The fixtures use
the field names and shapes from the hooks reference, so a change in the hook
contract shows up here rather than in a user's session.
"""

import json
import os

import pytest

from selfimprove import capture, store
from tests.conftest import PLUGIN_ROOT

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "hooks")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


def test_every_registered_hook_event_has_a_fixture():
    with open(os.path.join(PLUGIN_ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    for event_name in manifest["hooks"]:
        path = os.path.join(FIXTURES, "%s.json" % event_name.lower())
        assert os.path.exists(path), "no fixture for %s" % event_name


def test_user_prompt_submit_fixture_starts_a_turn(run_si, state_root):
    result = run_si("capture-prompt", stdin=fixture("userpromptsubmit.json"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "", "capture hooks must be silent"

    record = store.read_record(store.TURNS, "prompt-1", subdir="session-1")
    assert record["markers"] == ["correction"]
    assert record["prompt"] == "no, use make test instead of pytest"


def test_post_tool_use_failure_fixture_records_a_bounded_event(run_si, state_root):
    result = run_si("capture-tool-failure", stdin=fixture("posttoolusefailure.json"))
    assert result.returncode == 0, result.stderr

    record = store.read_record(store.TURNS, "prompt-1", subdir="session-1")
    [event] = record["events"]
    assert event["signature"] == "Bash:pytest"
    assert event["error_class"] == "nonzero_exit"
    assert "tests/unit" not in json.dumps(record)


def test_post_tool_use_fixture_pairs_with_the_prior_failure(run_si, state_root):
    run_si("capture-tool-failure", stdin=fixture("posttoolusefailure.json"))
    result = run_si("capture-tool-success", stdin=fixture("posttooluse.json"))
    assert result.returncode == 0, result.stderr

    record = store.read_record(store.TURNS, "prompt-1", subdir="session-1")
    successes = [e for e in record["events"] if e["kind"] == capture.TOOL_SUCCESS]
    assert successes and successes[0]["after_failure"] is True


def test_user_prompt_expansion_fixture_grants_authorization(run_si, state_root):
    result = run_si("capture-expansion", stdin=fixture("userpromptexpansion.json"))
    assert result.returncode == 0, result.stderr
    [record] = store.list_records(store.AUTHORIZATIONS)
    assert record["operation"] == "apply"
    assert record["proposal_id"] == "prop-abc123def456"


def test_session_end_fixture_sweeps(run_si, state_root):
    store.write_record(store.TURNS, "old", {}, ttl=-1, subdir="session-1")
    result = run_si("session-end", stdin=fixture("sessionend.json"))
    assert result.returncode == 0, result.stderr
    assert store.read_record(store.TURNS, "old", subdir="session-1", allow_expired=True) is None


@pytest.mark.parametrize(
    "subcommand",
    [
        "capture-prompt",
        "capture-tool-failure",
        "capture-tool-success",
        "capture-expansion",
        "session-end",
    ],
)
@pytest.mark.parametrize("payload", ["", "   ", "not json", "[]", "null", '{"a":1}'])
def test_capture_fails_open_on_any_input(run_si, state_root, subcommand, payload):
    """Section 11: a capture failure must never disturb the completed task."""
    result = run_si(subcommand, stdin=payload)
    assert result.returncode == 0, result.stderr


def test_capture_survives_an_unwritable_state_root(run_si, tmp_path):
    """A broken state directory must not surface as a hook error."""
    blocked = tmp_path / "blocked"
    blocked.mkdir(mode=0o500)
    try:
        result = run_si(
            "capture-prompt",
            stdin=fixture("userpromptsubmit.json"),
            env={"SELF_IMPROVE_STATE_DIR": str(blocked / "state")},
        )
        assert result.returncode == 0
    finally:
        blocked.chmod(0o700)
