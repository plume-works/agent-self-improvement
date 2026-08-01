"""Spec-0002: the asynchronous wake, verified without a person watching.

This is the automated counterpart to check 2 of the packaged smoke test. It
drives a real interactive Claude Code session on a pseudo-terminal, scripts the
correcting exchange, then types nothing and waits to see whether the review
comes back on its own.

It is opt-in for the reasons the spec sets out — it spends real model usage, it
is the least stable component in the repository, and a flaky assertion about the
wake would be worse than no assertion. It runs behind ``make wake`` and is
excluded from ``make test``, ``make check``, and ``make smoke``.

Two tests, and the second is the one that makes the first mean anything:

- ``arrives`` asserts a wake reaches an idle session;
- ``does_not_arrive`` runs the identical script against a plugin whose Stop hook
  never signals, and asserts the harness sees no wake.

The negative control deliberately does not simply drop ``asyncRewake``, which is
what Spec-0002 section 6 suggested. Without the flag the hook still runs and
still exits 2 — synchronously, inside the turn — so Claude is still told about
the candidate and the marker still reaches the screen. That control would pass
whether or not the wake mechanism worked. Suppressing the exit signal while
leaving everything else in place isolates the wake itself: the candidate is
stored exactly as before, and only the wake is missing.
"""

import json
import os
import pathlib
import shutil
import sys
import time

import pytest

from tests.smoke.conftest import (
    CORRECTION,
    FIRST_TURN,
    INTERACTIVE_ALLOWED_TOOLS,
    PLUGIN_ROOT,
    require_cli,
    runner_environment,
    seed_runnable_project,
    session_args,
)
from tests.smoke.pty_harness import (
    STARTUP_TIMEOUT,
    TURN_TIMEOUT,
    Deadline,
    Expired,
    PtySession,
    Trace,
)

pytestmark = pytest.mark.pty

# A permission prompt is fatal here in a way it is not headlessly: the session
# stops and waits, the turn never ends, no Stop hook fires, and the wake under
# test can never happen. Nothing answers prompts for us — that would mean
# reading the interface — so every way the first turn might reasonably run the
# suite is allowed up front. An unlisted command fails the run with a readable
# message instead of executing something nobody reviewed.
WAKE_ALLOWED_TOOLS = [
    *INTERACTIVE_ALLOWED_TOOLS,
    "Bash(python3:*)", "Bash(python:*)", "Bash(uv:*)", "Bash(env:*)",
]

# The wake follows a real model review of a completed turn, which is fast; the
# manual procedure's two-minute wait is a person's patience, not a measurement.
# These are step limits, and the whole check is bounded again by CHECK_BUDGET,
# so a stall anywhere fails with the screen attached instead of hanging.
WAKE_TIMEOUT = 60.0
CANDIDATE_TIMEOUT = 60.0


def report(label, detail=""):
    sys.stdout.write("\n  [wake] %s%s\n" % (label, (" " + detail) if detail else ""))
    sys.stdout.flush()


def candidate_ids(state):
    directory = os.path.join(str(state), "candidates")
    if not os.path.isdir(directory):
        return []
    return sorted(name[: -len(".json")] for name in os.listdir(directory)
                  if name.endswith(".json"))


def read_json(path):
    try:
        with open(str(path), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def read_diagnostics(state):
    """Every journaled record, or nothing if the file was never written."""
    path = os.path.join(str(state), "diagnostics.jsonl")
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
    return records


def launch(project, plugin_root, deadline, auto_memory=None):
    session = PtySession(
        ["claude", "--plugin-dir", str(plugin_root), *session_args(),
         "--allowedTools", *WAKE_ALLOWED_TOOLS],
        cwd=project, env=runner_environment(auto_memory), deadline=deadline,
    )
    return session.start()


def drive_the_correcting_exchange(session, deadline):
    """Two prompts, each its own turn, then silence.

    Anything typed mid-turn is folded into the turn already running, so the
    correction would never arrive as a prompt of its own and the gate would see
    no signal. Waiting for quiescence between them is what keeps them separate.

    Every step echoes the screen it produced. The harness types blind, so this
    is the only record of whether a prompt was captured as a prompt — and a
    correction folded into the previous turn looks, in plugin state, exactly
    like a review that decided against proposing anything.
    """
    if not session.wait_until_quiet(timeout=STARTUP_TIMEOUT, label="startup"):
        raise Expired("the session never settled after starting")
    session.trace.echo("startup", session.screen())
    deadline.check("after startup")

    # A first-run trust dialog would otherwise sit there forever. Enter accepts
    # its default; on a session that has no dialog it submits an empty prompt,
    # which does nothing. This is not a match on the interface — nothing is read
    # to decide it, it is sent unconditionally.
    session.send_line("")
    session.wait_until_quiet(quiet=2.0, timeout=STARTUP_TIMEOUT, label="dialog")
    session.trace.echo("dialog", session.screen())
    deadline.check("after clearing any startup dialog")

    session.send_line(FIRST_TURN)
    if not session.wait_until_quiet(timeout=TURN_TIMEOUT, label="turn-1"):
        raise Expired("the first turn never finished")
    session.trace.echo("turn-1", session.screen())
    deadline.check("after the first turn")

    session.send_line(CORRECTION)
    if not session.wait_until_quiet(timeout=TURN_TIMEOUT, label="turn-2"):
        raise Expired("the correcting turn never finished")
    session.trace.echo("turn-2", session.screen())
    deadline.check("after the correcting turn")


def await_candidate(session, state, timeout=CANDIDATE_TIMEOUT):
    """Wait for review to store a candidate, reading the pty meanwhile.

    Disk first, screen second, always. Learning the identifier here is what lets
    the single on-screen match be for a string the plugin generated rather than
    for wording someone chose.
    """
    session.watch(lambda: bool(candidate_ids(state)), timeout=timeout,
                  label="candidate-on-disk")
    return candidate_ids(state)


def forensics(state, session):
    lines = ["state root: %s" % state,
             "raw terminal stream: %s.pty.log, beside the workspace"
             % session.trace.name]
    for name in ("candidates", "turns"):
        path = os.path.join(str(state), name)
        lines.append("%s: %s" % (name, sorted(os.listdir(path))
                                 if os.path.isdir(path) else "(none)"))
    for name in ("counters.json", "pending.json", "diagnostics.jsonl"):
        path = os.path.join(str(state), name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                lines.append("%s: %s" % (name, handle.read().strip()[-600:]))
        else:
            lines.append("%s: (none)" % name)
    lines.append("screen tail:\n%s" % session.tail())
    return "\n".join(lines)


def no_wake_plugin(workspace):
    """A copy of the plugin whose Stop hook can never signal a wake.

    Everything else is the packaged plugin: the same capture hooks, the same
    gate, the same reviewer, the same candidate written to the same state root.
    Only the exit code that asks Claude to wake is thrown away.
    """
    root = pathlib.Path(workspace) / "plugin-no-wake"
    if root.exists():
        shutil.rmtree(str(root))
    shutil.copytree(PLUGIN_ROOT, str(root),
                    ignore=shutil.ignore_patterns("__pycache__"))

    silent = root / "scripts" / "si-silent"
    silent.write_text(
        "#!/bin/sh\n"
        "# Negative control (Spec-0002 section 6.2): run review exactly as the\n"
        "# packaged hook does, then discard its exit code so no wake is ever\n"
        "# signalled.\n"
        '"$(dirname "$0")/si" "$@"\n'
        "exit 0\n"
    )
    silent.chmod(0o755)

    hooks_path = root / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text())
    for entry in hooks["hooks"]["Stop"]:
        for hook in entry["hooks"]:
            hook["command"] = hook["command"].replace("/scripts/si",
                                                      "/scripts/si-silent")
    hooks_path.write_text(json.dumps(hooks, indent=2) + "\n")
    return root


def run_exchange(scratch, plugin_root, name="wake", auto_memory=None):
    """The whole scripted run, returning the session and what state it produced.

    Bounded end to end by one budget. A working run takes well under a minute;
    anything that stalls fails here with the screen attached rather than
    occupying a terminal until someone kills it.

    Traced end to end as well, live rather than afterwards: the trace names the
    step it is inside, repeats itself every few seconds while a wait is running,
    and leaves the raw terminal stream in the workspace next to the plugin state
    it produced.
    """
    require_cli()
    seed_runnable_project(scratch["project"])

    trace = Trace(name, directory=scratch["workspace"])
    deadline = Deadline(trace=trace)
    trace.event("budget", "%.0fs for this check" % deadline.budget)
    session = launch(scratch["project"], plugin_root, deadline, auto_memory)
    candidates = []
    woke = False
    try:
        drive_the_correcting_exchange(session, deadline)
        waited = time.time()
        candidates = await_candidate(session, scratch["state"])
        waited = time.time() - waited
        trace.event("candidates", str(candidates) or "(none)")
        if candidates:
            woke = session.watch(lambda: session.contains(candidates[0]),
                                 timeout=WAKE_TIMEOUT,
                                 label="wake-on-screen")
            trace.echo("after-wake-wait", session.screen())
        elif waited < CANDIDATE_TIMEOUT - 1:
            # The wait was cut short by the budget rather than by its own limit,
            # so review may simply be late. A late review is a different failure
            # from a missing wake; spend what is left telling them apart.
            session.watch(lambda: bool(candidate_ids(scratch["state"])),
                          timeout=WAKE_TIMEOUT, label="late-candidate")
            candidates = candidate_ids(scratch["state"])
        else:
            # Review had its full window and stored nothing. Waiting the same
            # window again cannot change that, and doubling a failing check's
            # runtime is what makes this harness feel like it has hung.
            trace.event("no candidate",
                        "review had its full %.0fs window and stored nothing; "
                        "not waiting again" % CANDIDATE_TIMEOUT)
        status = session.close()
    except Expired as expiry:
        status = session.close()
        pytest.fail("%s after %.0fs.\nA working run finishes in well under a "
                    "minute, so this is a stalled session rather than a slow "
                    "one — most often a turn waiting on a permission prompt or "
                    "a dialog.\nsession exit: %r\n%s"
                    % (expiry, deadline.elapsed(), status,
                       forensics(scratch["state"], session)))
    finally:
        if session.process is not None and session.process.poll() is None:
            session.close()
    return session, candidates, woke, status


# The wake ------------------------------------------------------------------

def test_the_async_wake_arrives_at_an_idle_session(scratch):
    """A completed correction wakes the session with nobody typing.

    The assertions are ordered so that a failure names what actually went
    wrong: review never ran, review ran and proposed nothing, or the candidate
    exists and the wake never landed.
    """
    session, candidates, woke, status = run_exchange(scratch, PLUGIN_ROOT,
                                                     name="wake-arrives")

    counters = read_json(os.path.join(str(scratch["state"]), "counters.json"))
    assert counters is not None, (
        "no review ever started, so nothing here says anything about the wake. "
        "The usual cause is a turn that never ended — a permission prompt for a "
        "command outside WAKE_ALLOWED_TOOLS leaves the session waiting, and no "
        "Stop hook fires for a turn that has not finished. Undiscarded turn "
        "files below are the signature of that.\n%s"
        % forensics(scratch["state"], session))

    assert candidates, (
        "review ran but stored no candidate, so there was nothing to wake with. "
        "That is a reviewer outcome, not a wake failure. The `review_outcome` "
        "record in the diagnostics below says which one: a discard category "
        "means the reviewer read the turn and declined, an error class means it "
        "was never reached, `duplicate` means the lesson was already known.\n%s"
        % forensics(scratch["state"], session))

    candidate_id = candidates[0]
    record = read_json(os.path.join(str(scratch["state"]), "candidates",
                                    candidate_id + ".json"))
    assert record and record.get("lesson"), \
        "the candidate record is unusable: %r" % (record,)

    pending = read_json(os.path.join(str(scratch["state"]), "pending.json")) or {}
    assert any(entry.get("candidate_id") == candidate_id
               for entry in pending.get("candidates", [])), (
        "the candidate was never queued, so a lost wake would not be "
        "recoverable at the next session start.\n%s"
        % forensics(scratch["state"], session))

    assert woke, (
        "the candidate %s was staged but its identifier never reached the "
        "screen: the review completed and the wake did not arrive.\n%s"
        % (candidate_id, forensics(scratch["state"], session)))

    assert status == 0, "the session did not exit cleanly (status %r)" % (status,)
    report("wake observed for candidate", candidate_id)
    report("lesson:", record["lesson"])


# Auto memory ---------------------------------------------------------------

@pytest.mark.auto_memory
def test_the_two_learning_systems_do_not_collide(scratch):
    """The same exchange with Claude Code's own auto memory left on.

    This is not a variant of the wake check; it is the interaction the wake
    check had to be insulated from, given a test of its own so that insulating
    it did not mean forgetting about it.

    Auto memory writes its lesson during the turn that teaches it, so by the
    time the Stop hook runs the lesson is already recorded — and this plugin's
    reviewer, seeing it owned, declines with `already_covered`. That is correct
    behaviour, not a failure, and it is why the wake check runs with auto memory
    off: the plugin was losing a race it should never have been entered into.

    So the assertion here is coherence, not a candidate. Exactly one of two
    things must happen, and either is a pass:

    - the reviewer declines because the lesson is already owned; or
    - it proposes anyway, and the wake arrives as it would otherwise.

    What fails is incoherence: no review at all, a reviewer that could not be
    reached, a candidate stored but never queued. Those would mean the two
    systems interfere rather than defer.
    """
    session, candidates, woke, status = run_exchange(
        scratch, PLUGIN_ROOT, name="wake-auto-memory", auto_memory=True)

    counters = read_json(os.path.join(str(scratch["state"]), "counters.json"))
    assert counters is not None, (
        "no review ran at all, so this says nothing about how the two systems "
        "interact.\n%s" % forensics(scratch["state"], session))

    if candidates:
        assert woke, (
            "the reviewer proposed alongside auto memory but the wake never "
            "arrived, which is a wake failure and not an interaction.\n%s"
            % forensics(scratch["state"], session))
        report("proposed despite auto memory", candidates[0])
    else:
        outcomes = [record for record in read_diagnostics(scratch["state"])
                    if record.get("stage") == "review_outcome"]
        assert outcomes, (
            "review ran, stored nothing, and recorded no outcome — the one "
            "combination that cannot be explained from state.\n%s"
            % forensics(scratch["state"], session))
        reasons = [record.get("reason") for record in outcomes]
        assert "already_covered" in reasons, (
            "the reviewer declined for %r rather than because the lesson was "
            "already owned. With auto memory on, the lesson is recorded during "
            "the turn, so `already_covered` is the outcome that shows the two "
            "systems deferring to each other rather than failing "
            "independently.\n%s" % (reasons, forensics(scratch["state"], session)))
        report("deferred to auto memory, as expected", reasons[0])

    assert status == 0, "the session did not exit cleanly (status %r)" % (status,)


# The control ---------------------------------------------------------------

def test_the_harness_fails_when_the_wake_does_not_arrive(scratch):
    """The same run against a Stop hook that never signals: no wake, by construction.

    Without this, a harness that could not see a wake at all would pass the test
    above only by accident of the wake being there.
    """
    plugin_root = no_wake_plugin(scratch["workspace"])
    session, candidates, woke, status = run_exchange(scratch, plugin_root,
                                                     name="wake-control")

    assert candidates, (
        "the control observed nothing: with no candidate stored, this run does "
        "not show that a suppressed wake is detected.\n%s"
        % forensics(scratch["state"], session))

    assert not woke, (
        "candidate %s reached the screen although the Stop hook never signalled "
        "a wake. Either the harness is matching something other than the wake, "
        "or the candidate reached Claude by another route.\n%s"
        % (candidates[0], forensics(scratch["state"], session)))

    assert status == 0, "the session did not exit cleanly (status %r)" % (status,)
    report("no wake, as expected, for staged candidate", candidates[0])


# Harness self-checks -------------------------------------------------------

def test_the_screen_matcher_survives_wrapping_and_styling():
    """The one on-screen match must not be defeated by the renderer.

    A candidate identifier that wraps at the margin, or that arrives with color
    around it, is still the same identifier. This is checked without a model,
    because getting it wrong shows up as a wake that "did not arrive".
    """
    from tests.smoke.pty_harness import flatten

    session = PtySession(["true"], cwd=os.getcwd(), env={})
    session.buffer = "self-improve: candidate cand-\r\n  \x1b[1mabc123def456\x1b[0m\n"
    assert session.contains("cand-abc123def456")
    assert not session.contains("cand-000000000000")
    assert flatten("\x1b[31ma b\nc\x1b[0m") == "abc"


def test_the_budget_bounds_a_session_that_never_stops_talking():
    """No wait may outlive the check's budget, however chatty the session is.

    The failure this prevents is the one that happened: every individual wait
    was inside its own limit and the check still ran for eighteen minutes.
    """
    deadline = Deadline(budget=3.0)
    session = PtySession(
        [sys.executable, "-c",
         "import sys, time\n"
         "while True:\n"
         "    sys.stdout.write('.'); sys.stdout.flush(); time.sleep(0.05)\n"],
        cwd=os.getcwd(), env=dict(os.environ), deadline=deadline).start()
    try:
        started = time.time()
        # Its own timeout is a minute; the budget is three seconds and wins.
        assert session.wait_until_quiet(timeout=60.0) is False
        assert time.time() - started < 15
        assert deadline.expired()
        with pytest.raises(Expired):
            deadline.check("afterwards")
    finally:
        session.close()


def test_the_harness_reports_a_session_it_had_to_kill():
    """A session that ignores /exit must not be reported as a clean exit."""
    session = PtySession([sys.executable, "-c",
                          "import signal, time\n"
                          "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                          "time.sleep(300)\n"],
                         cwd=os.getcwd(), env=dict(os.environ)).start()
    started = time.time()
    assert session.close(timeout=2) is None
    assert time.time() - started < 60
