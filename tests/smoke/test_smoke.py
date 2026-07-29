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
    PLUGIN_ROOT,
    ask,
    expansion,
    run_session,
    si,
)

pytestmark = pytest.mark.smoke

CORRECTION = (
    "Run the project's test suite. Then note: no, don't run pytest directly in "
    "this repository, always run the suite with `make test` because it sets the "
    "required environment variables first. Please remember that for the future."
)


def report(label, detail=""):
    sys.stdout.write("\n  [smoke] %s%s\n" % (label, (" " + detail) if detail else ""))
    sys.stdout.flush()


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
        return next(i for i, event in enumerate(result.events) if predicate(event))

    assistant_at = index_of(lambda e: e.get("type") == "assistant")
    stop_at = index_of(lambda e: e.get("type") == "system"
                       and e.get("subtype") == "hook_started"
                       and e.get("hook_event") == "Stop")
    assert assistant_at < stop_at, "the reply must be emitted before review begins"

    fired = sorted({e.get("hook_event") for e in result.hook_events()})
    report("plugin loaded; hooks fired:", ", ".join(fired))


# Check 3 -------------------------------------------------------------------

def test_3_a_real_reviewer_produces_a_schema_valid_candidate(scratch):
    """The reviewer prompt meeting a real model for the first time.

    Everything offline uses a deterministic fake, so this is the only place the
    committed prompt and the schema validator are tested against the thing they
    were written for.
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
        pytest.fail(
            "the real reviewer returned %r for an explicit correction with a "
            "stated reason and a request to remember it. Either the prompt is "
            "too conservative or the model disagreed; check "
            "%s/diagnostics.jsonl" % (payload, scratch["state"]))

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

    sys.stdout.write("""
==============================================================================
  Check 2: does the asynchronous review wake an idle session?

  An interactive Claude Code session is about to open in this terminal, in a
  scratch repository that is already set up. Nothing else is needed from you
  beforehand.

  Inside that session:

    1. Type this, or anything that corrects a real approach:

         run the tests with pytest

       then, after it replies:

         no, always use `make test` in this repo, not pytest directly

    2. Wait up to a minute WITHOUT typing anything.

       Expected: the session wakes on its own with a self-improve notice
       naming a candidate, and Claude offers a proposal.

    3. Type /exit to come back here.

  Working directory: %s
  Plugin state:      %s
==============================================================================
""" % (scratch["project"], scratch["state"]))
    sys.stdout.flush()
    input("  Press Enter to launch the session... ")

    subprocess.run(["claude", "--plugin-dir", PLUGIN_ROOT],
                   cwd=str(scratch["project"]), check=False)

    # Whatever you saw, these are checkable: the review has to have run.
    candidates_dir = os.path.join(str(scratch["state"]), "candidates")
    candidates = (os.listdir(candidates_dir) if os.path.isdir(candidates_dir) else [])
    diagnostics = os.path.join(str(scratch["state"]), "diagnostics.jsonl")

    woke = ask("Did the session wake on its own with a self-improve candidate?")
    if woke is None:
        pytest.skip("no answer given")

    if not woke:
        detail = ""
        if os.path.exists(diagnostics):
            with open(diagnostics, encoding="utf-8") as handle:
                detail = handle.read()[-800:]
        pytest.fail(
            "the asynchronous wake did not reach the session.\n"
            "candidates on disk: %s\n"
            "diagnostics:\n%s\n"
            "workspace kept at %s" % (candidates, detail or "(none)",
                                      scratch["workspace"]))

    assert candidates, (
        "you saw a wake but no candidate was stored; the wake and the state "
        "disagree, which is worth investigating at %s" % scratch["state"])
    report("async wake confirmed, candidate on disk:", candidates[0])
