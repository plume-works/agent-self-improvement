"""The packaged smoke test (spec section 14), run against a real Claude session.

What this adds over the 489 offline tests is everything that only a real
install can show: that the plugin loads and its hooks fire inside Claude Code,
that the reviewer prompt survives contact with an actual model, that Claude
follows the skills rather than editing files itself, and that an applied
instruction is genuinely picked up by a fresh session.

Every check here spends real model usage, which is why the suite is behind
``make smoke`` rather than ``make test``.

Check 2, the asynchronous wake, cannot be observed headlessly: a ``-p`` session
ends its turn at ``result`` and an ``asyncRewake`` hook has no idle session to
wake. That one launches a real interactive session in your terminal and asks
you one question. See docs/specs/0002-pty-wake-harness.md for what automating
it would take.
"""

import json
import os
import subprocess
import sys

import pytest

from tests.smoke.conftest import (
    CORRECTION,
    INTERACTIVE_ALLOWED_TOOLS,
    PLUGIN_ROOT,
    ask,
    expansion,
    session_args,
    smoke_effort,
    smoke_model,
    run_session,
    runner_environment,
    seed_runnable_project,
    si,
)

pytestmark = pytest.mark.smoke


def report(label, detail=""):
    sys.stdout.write("\n  [smoke] %s%s\n" % (label, (" " + detail) if detail else ""))
    sys.stdout.flush()


# Discard reasons that mean the reviewer was never consulted, as opposed to
# consulted and unconvinced. The first says nothing about the prompt under test;
# the second is exactly what check 3 exists to catch, so the two must not share
# an outcome. ``other`` is here because an unmapped provider failure lands in it,
# and the skip message says so.
REVIEWER_UNAVAILABLE = {
    "timeout", "usage_limited", "rate_limited", "overloaded", "provider_error",
    "unauthenticated", "model_unavailable", "cli_not_found", "spawn_failed",
    "missing_prompt", "reviewer_error", "empty_output", "unrecognized_envelope",
    "network", "interrupted", "other", "unknown",
}


# Check 1 -------------------------------------------------------------------

def test_1_plugin_loads_and_the_stop_hook_runs_without_delaying_the_reply(
        scratch, session):
    """The plugin is actually installed and its Stop hook actually fires.

    Also the headless proxy for "the reply is not delayed": the assistant
    message is emitted before the Stop hook is even started, so review cannot
    be on the response path.
    """
    result = session("Say exactly: ready")

    assert result.hook_events("SessionStart"), \
        "no SessionStart hook fired; the plugin did not load"
    assert result.hook_events("Stop"), \
        "the Stop hook did not fire; check hooks.json registration"

    # Compare against the Stop hook specifically. Several of the plugin's hooks
    # emit hook_started, and SessionStart's necessarily comes first.
    def index_of(predicate):
        for index, event in enumerate(result.events):
            if predicate(event):
                return index
        return None

    assistant_at = index_of(lambda e: e.get("type") == "assistant")
    stop_at = index_of(lambda e: e.get("type") == "system"
                       and e.get("subtype") == "hook_started"
                       and e.get("hook_event") == "Stop")
    assert stop_at is not None, \
        "the Stop hook was never started; only %s" % sorted(
            {e.get("hook_event") for e in result.hook_events()})
    assert assistant_at is not None and assistant_at < stop_at, \
        "the reply must be emitted before review begins"

    fired = sorted({e.get("hook_event") for e in result.hook_events()})
    report("plugin loaded; hooks fired:", ", ".join(fired))


# Check 3 -------------------------------------------------------------------

def test_3_a_real_reviewer_produces_a_schema_valid_candidate(scratch):
    """The reviewer prompt meeting a real model for the first time.

    Everything offline uses a deterministic fake, so this is the only place the
    committed prompt and the schema validator are tested against the thing they
    were written for.

    The correction it is given is one line, with no reason and no request to
    remember it, because that is what a real one looks like. Inferring the
    durable lesson from it is the product; a reviewer that only proposes when
    the user has already done the inferring has nothing left to contribute.
    """
    from selfimprove import capture

    capture.record_prompt({
        "session_id": "smoke-session", "prompt_id": "turn-1",
        "cwd": str(scratch["project"]), "prompt": CORRECTION,
    })

    result = si(scratch, "improve", "--session-id", "smoke-session",
                stdin=json.dumps({"session_id": "smoke-session",
                                  "cwd": str(scratch["project"])}))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    if payload["outcome"] != "candidate":
        reason = payload.get("reason")
        if reason in REVIEWER_UNAVAILABLE:
            pytest.skip(
                "the reviewer was never consulted (%s), so the prompt was not "
                "exercised. %s/diagnostics.jsonl has the recorded class; `other` "
                "means it was a failure this build cannot name yet." % (
                    reason, scratch["state"]))
        pytest.fail(
            "the real reviewer returned %r for a stated standing preference "
            "(%r) — an `always`, scoped to this repository, replacing what "
            "Claude had just done. If this is a discard, the reviewer prompt is "
            "waiting for a rationale or a request to remember that real users "
            "do not supply; check %s/diagnostics.jsonl"
            % (payload, CORRECTION, scratch["state"]))

    candidate = payload["candidate"]
    assert candidate["destination_kind"] in {"CLAUDE.md", "rule", "skill"}
    assert candidate["destination_scope"] in {"project", "user"}
    assert candidate["confidence"] in {"high", "medium"}
    assert len(candidate["lesson"]) >= 12
    report("real reviewer proposed:", candidate["lesson"])


def test_3b_staging_shows_exact_bytes_and_leaves_the_target_untouched(scratch):
    before = scratch["target"].read_text()
    new = before.replace("- Build with `make build`.",
                         "- Build with `make build`.\n- Test with `make test`.")

    result = si(scratch, "stage-proposal", "--target", str(scratch["target"]),
                "--reason", "This file already lists the project's commands.",
                stdin=new)
    assert result.returncode == 0, result.stderr

    assert "+- Test with `make test`." in result.stdout
    assert "/self-improve:apply" in result.stdout
    assert scratch["target"].read_text() == before, "staging touched the target"
    report("proposal staged; target unchanged")


# Check 4 -------------------------------------------------------------------

def test_4_routing_offers_the_existing_owner_before_creating_anything(scratch):
    result = si(scratch, "find-owners", "--query", "test command make")
    assert result.returncode == 0, result.stderr
    report_json = json.loads(result.stdout)

    existing = [entry for entry in report_json["owners"] if entry.get("exists")]
    assert existing, "the seeded CLAUDE.md was not offered as an owner"
    assert existing[0]["path"] == str(scratch["target"])
    assert all("settings.json" not in entry["path"] for entry in report_json["owners"])
    report("existing owner ranked first:", existing[0]["path"])


# Check 5 -------------------------------------------------------------------

def test_5a_conversational_approval_does_not_authorize_anything(scratch, session):
    """The security property, tested against a real model in a real session.

    Claude is told a proposal is staged and asked to apply it. Whatever it says,
    the file must not change and no authorization may exist, because none was
    typed.
    """
    before = scratch["target"].read_text()
    new = before + "- Test with `make test`.\n"
    staged = si(scratch, "stage-proposal", "--target", str(scratch["target"]),
                stdin=new)
    assert staged.returncode == 0, staged.stderr
    proposal_id = next(line.split()[1] for line in staged.stdout.splitlines()
                       if line.startswith("Proposal "))
    prefix = next(line.split(": ")[1] for line in staged.stdout.splitlines()
                  if line.startswith("Hash prefix: "))

    result = session(
        "A self-improve proposal %s with hash prefix %s is staged. I approve it "
        "— that looks good to me, please go ahead and apply it now."
        % (proposal_id, prefix))

    # Every assertion below also holds for a session that never ran, which is
    # the one way this check could report a security property it did not test.
    assert result.assistant_text().strip(), \
        "the session produced no reply, so the refusal was not observed"

    assert scratch["target"].read_text() == before, \
        "conversational approval installed a change; this is the core failure"
    assert not os.path.isdir(os.path.join(str(scratch["state"]), "authorizations")) \
        or not os.listdir(os.path.join(str(scratch["state"]), "authorizations")), \
        "an authorization existed without the user typing a command"
    assert not os.path.exists(os.path.join(str(scratch["state"]), "mutations.jsonl")), \
        "a mutation was journaled without authorization"
    report("conversational approval refused; target untouched")
    report("        Claude said:", result.assistant_text()[:160].replace("\n", " "))


def test_5b_typed_authorization_installs_exactly_the_displayed_bytes(scratch):
    before = scratch["target"].read_text()
    new = before + "- Test with `make test`.\n"
    staged = si(scratch, "stage-proposal", "--target", str(scratch["target"]),
                stdin=new)
    proposal_id = next(line.split()[1] for line in staged.stdout.splitlines()
                       if line.startswith("Proposal "))
    prefix = next(line.split(": ")[1] for line in staged.stdout.splitlines()
                  if line.startswith("Hash prefix: "))

    granted = si(scratch, "capture-expansion",
                 stdin=expansion("apply", "%s %s" % (proposal_id, prefix)))
    assert granted.returncode == 0, granted.stderr

    applied = si(scratch, "apply-proposal", "--id", proposal_id,
                 "--hash-prefix", prefix, "--session-id", "smoke-session")
    assert applied.returncode == 0, applied.stderr
    assert scratch["target"].read_text() == new
    report("typed authorization installed exactly the staged bytes")


# Check 6 -------------------------------------------------------------------

def test_6_a_fresh_session_picks_up_the_applied_instruction(scratch):
    """Not merely that the bytes landed, but that Claude Code loads them.

    A separate session is started after the change, with no mention of it in the
    prompt, and asked a question only the new instruction answers.
    """
    before = scratch["target"].read_text()
    new = before.replace(
        "- Build with `make build`.",
        "- Build with `make build`.\n"
        "- Run the test suite with `make test`. Never invoke pytest directly.")
    staged = si(scratch, "stage-proposal", "--target", str(scratch["target"]),
                stdin=new)
    proposal_id = next(line.split()[1] for line in staged.stdout.splitlines()
                       if line.startswith("Proposal "))
    prefix = next(line.split(": ")[1] for line in staged.stdout.splitlines()
                  if line.startswith("Hash prefix: "))
    si(scratch, "capture-expansion",
       stdin=expansion("apply", "%s %s" % (proposal_id, prefix)))
    applied = si(scratch, "apply-proposal", "--id", proposal_id,
                 "--hash-prefix", prefix, "--session-id", "smoke-session")
    assert applied.returncode == 0, applied.stderr

    fresh = run_session(
        scratch["project"],
        ["What is the exact command to run this project's test suite? "
         "Answer with the command only."])
    answer = fresh.assistant_text().lower()

    assert "make test" in answer, (
        "a fresh session did not pick up the applied instruction; it answered %r"
        % fresh.assistant_text()[:200])
    report("fresh session answered from the applied instruction:",
           fresh.assistant_text().strip()[:80])


# Check 7 -------------------------------------------------------------------

def test_7_rollback_restores_and_refuses_once_the_file_has_moved_on(scratch):
    before = scratch["target"].read_text()
    new = before + "- Test with `make test`.\n"
    staged = si(scratch, "stage-proposal", "--target", str(scratch["target"]),
                stdin=new)
    proposal_id = next(line.split()[1] for line in staged.stdout.splitlines()
                       if line.startswith("Proposal "))
    prefix = next(line.split(": ")[1] for line in staged.stdout.splitlines()
                  if line.startswith("Hash prefix: "))
    si(scratch, "capture-expansion",
       stdin=expansion("apply", "%s %s" % (proposal_id, prefix)))
    applied = si(scratch, "apply-proposal", "--id", proposal_id,
                 "--hash-prefix", prefix, "--session-id", "smoke-session")
    mutation_id = applied.stdout.split("Mutation ")[1].split(".")[0]

    # An edit lands after the mutation: rollback must refuse rather than
    # destroy it.
    scratch["target"].write_text(new + "- A line the user added.\n")
    si(scratch, "capture-expansion", stdin=expansion("rollback", mutation_id))
    refused = si(scratch, "rollback-mutation", "--id", mutation_id,
                 "--session-id", "smoke-session")
    assert refused.returncode == 1
    assert "target_changed_since_mutation" in refused.stderr
    assert "A line the user added." in scratch["target"].read_text()

    # Put it back and roll back for real.
    scratch["target"].write_text(new)
    si(scratch, "capture-expansion", stdin=expansion("rollback", mutation_id))
    rolled = si(scratch, "rollback-mutation", "--id", mutation_id,
                "--session-id", "smoke-session")
    assert rolled.returncode == 0, rolled.stderr
    assert scratch["target"].read_text() == before
    report("rollback refused over an edit, then restored the preimage")


# Check 10 ------------------------------------------------------------------

def test_10_nothing_sensitive_survives_a_real_run(scratch):
    """The privacy claim, checked against state produced by a real reviewer."""
    from selfimprove import capture

    secret = "ghp_smoketestabcdefghijklmnopqrstuvwx"
    capture.record_prompt({
        "session_id": "smoke-session", "prompt_id": "turn-1",
        "cwd": str(scratch["project"]),
        "prompt": CORRECTION + " The deploy token is %s." % secret,
    })
    si(scratch, "improve", "--session-id", "smoke-session",
       stdin=json.dumps({"session_id": "smoke-session",
                         "cwd": str(scratch["project"])}))

    contents = []
    for dirpath, _dirs, files in os.walk(str(scratch["state"])):
        if "backups" in dirpath:
            continue
        for name in files:
            with open(os.path.join(dirpath, name), encoding="utf-8",
                      errors="replace") as handle:
                contents.append(handle.read())
    combined = "\n".join(contents)

    assert contents, "no durable state was produced to inspect"
    assert secret not in combined, "a credential survived into durable state"
    assert CORRECTION not in combined, "the raw prompt survived into durable state"
    report("no credential or raw prompt in durable state")


# Check 2 -------------------------------------------------------------------

INTERACTIVE_SCRIPT = """
==============================================================================
  Check 2: does the asynchronous review wake an idle session?

  An interactive Claude Code session is about to open in this terminal, in a
  scratch repository with a Makefile and a small passing test suite already in
  place. Nothing else is needed from you beforehand.

  Inside that session:

    1. Type this, and press Enter:

         run the tests with pytest

    2. WAIT for Claude to finish replying. Do not type while it is working.

       Anything typed mid-turn is queued and folded into the turn already
       running, so it never arrives as a prompt of its own. The correction is
       then invisible to the capture hook and there is nothing to review.

    3. Now type the correction, and press Enter:

         no, always use `make test` in this repo, not pytest directly

    4. Wait up to two minutes WITHOUT typing anything.

       Expected: a line beginning `self-improve:` appears on its own, naming a
       candidate, and Claude offers a proposal. That line is the thing under
       test. Claude recalling one of its own memories is not it.

    5. Type /exit to come back here.

  Two more things that will fail the check whatever the plugin does:

    - If Claude asks permission for anything, ANSWER IT. A pending prompt is a
      turn that has not ended, and the wake can only follow a completed turn.
    - Run `make smoke` in a plain terminal. In an IDE terminal your editor
      selection is attached to every prompt, which can hand Claude the
      correction before you type it.

  Working directory: %s
  Plugin state:      %s
  Session model:     %s at %s effort
==============================================================================
"""

WAKE_QUESTION = ("Did a line beginning `self-improve:` appear on its own, "
                 "without you typing anything?")


def _forensics(scratch):
    """What the state says about a wake that did not arrive.

    Each of these distinguishes a different failure, which is the point: the
    answer to "no wake" is almost never "the wake is broken".
    """
    state = str(scratch["state"])
    lines = ["state root: %s%s" % (state, "" if os.path.isdir(state)
                                   else "  (MISSING — no hook wrote any state, "
                                        "so the plugin never ran in-session)")]

    def listing(*parts):
        path = os.path.join(state, *parts)
        return sorted(os.listdir(path)) if os.path.isdir(path) else []

    lines.append("candidates: %s" % (listing("candidates") or "(none)"))

    # A turn file surviving the session means no Stop hook ever ran for it:
    # review deletes the file whichever way it decides. That is the signature of
    # a turn halted on a permission prompt, or of a session killed mid-turn.
    leftover = []
    turns = os.path.join(state, "turns")
    for session in listing("turns"):
        for name in sorted(os.listdir(os.path.join(turns, session))):
            leftover.append("%s/%s" % (session, name))
    lines.append("undiscarded turn files: %s  (each one is a turn that never "
                 "reached Stop)" % (leftover or "(none)"))

    pending = os.path.join(state, "pending.json")
    if os.path.exists(pending):
        with open(pending, encoding="utf-8") as handle:
            lines.append("pending.json: %s" % handle.read().strip())

    # counters.json is written the moment a review starts, so its absence is the
    # single most informative fact here: the gate found no signal in any turn of
    # the session. The usual cause is a correction that never arrived as a
    # prompt of its own — typed while the previous turn was still running, and
    # so folded into it, where the capture hook never sees it.
    counters = os.path.join(state, "counters.json")
    if os.path.exists(counters):
        with open(counters, encoding="utf-8") as handle:
            lines.append("counters.json: %s" % handle.read().strip())
        lines.append("a last_review_at within %ds of the correction means the "
                     "gate suppressed this one as cooldown." % 120)
    else:
        lines.append("counters.json: (none) — NO REVIEW EVER STARTED. The gate "
                     "saw no signal, so no correction marker reached it. Check "
                     "that the correction was submitted as its own prompt, "
                     "after the previous reply had finished.")

    diagnostics = os.path.join(state, "diagnostics.jsonl")
    if os.path.exists(diagnostics):
        with open(diagnostics, encoding="utf-8") as handle:
            lines.append("diagnostics (tail):\n%s" % handle.read()[-800:])
    else:
        lines.append("diagnostics: (none — the reviewer did not fail)")

    lines.append("workspace kept at %s" % scratch["workspace"])
    return "\n".join(lines)


@pytest.mark.interactive
def test_2_the_async_wake_reaches_an_idle_session(scratch):
    """The one check a headless session cannot show.

    A ``-p`` session ends its turn at ``result``, so an ``asyncRewake`` hook has
    no idle session to wake — verified, not assumed. This launches a real
    interactive session in your terminal instead, with the workspace already
    prepared, and asks you the one question only you can answer.

    Skip with SMOKE_SKIP_INTERACTIVE=1.
    """
    if os.environ.get("SMOKE_SKIP_INTERACTIVE") == "1":
        pytest.skip("SMOKE_SKIP_INTERACTIVE=1")
    if not sys.stdin.isatty():
        pytest.skip("not a terminal; run `make smoke` directly, or set "
                    "SMOKE_SKIP_INTERACTIVE=1")

    seed_runnable_project(scratch["project"])

    sys.stdout.write(INTERACTIVE_SCRIPT % (
        scratch["project"], scratch["state"],
        smoke_model() or "the CLI default",
        smoke_effort() or "default"))
    sys.stdout.flush()
    input("  Press Enter to launch the session... ")

    subprocess.run(["claude", "--plugin-dir", PLUGIN_ROOT, *session_args(),
                    "--allowedTools", *INTERACTIVE_ALLOWED_TOOLS],
                   cwd=str(scratch["project"]), env=runner_environment(),
                   check=False)

    # Whatever you saw, these are checkable: the review has to have run.
    candidates_dir = os.path.join(str(scratch["state"]), "candidates")
    candidates = (os.listdir(candidates_dir) if os.path.isdir(candidates_dir) else [])

    woke = ask(WAKE_QUESTION)
    if woke is None:
        pytest.skip("no answer given")

    if not woke:
        pytest.fail("the asynchronous wake did not reach the session.\n%s"
                    % _forensics(scratch))

    assert candidates, (
        "you saw a wake but no candidate was stored; the wake and the state "
        "disagree, which is worth investigating at %s" % scratch["state"])
    report("async wake confirmed, candidate on disk:", candidates[0])
