"""Subcommand implementations.

The dispatcher owns argument routing and the fail-open rule; each function here
owns one operation. Handlers are registered in :data:`HANDLERS` as they are
implemented, so an unimplemented subcommand is a parser error rather than a stub
that silently succeeds.
"""

import argparse
import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys

from . import (
    allowlist,
    authz,
    capture,
    config,
    gate,
    hookio,
    journal,
    mutate,
    orchestrate,
    owners,
    paths,
    proposals,
    store,
)


def _emit(payload):
    json.dump(payload, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


def _fail(reason, detail=None):
    sys.stderr.write("self-improve: %s%s\n"
                     % (reason, " (%s)" % detail if detail else ""))
    return 1


def capture_prompt(argv):
    """Start a turn and note its markers (spec section 5.1).

    Silent by design: no stdout, so nothing enters the transcript. This hook
    runs before every prompt on a five-second budget.
    """
    capture.record_prompt(hookio.read_event())
    return 0


def capture_tool_failure(argv):
    capture.record_tool_failure(hookio.read_event())
    return 0


def capture_tool_success(argv):
    capture.record_tool_success(hookio.read_event())
    return 0


def review_turn(argv):
    """The Stop hook (spec section 5.5).

    Runs in the background under ``asyncRewake``, so the user's response is
    never delayed. Exit 0 stays silent; exit 2 wakes the session with the
    message on stderr, which is the documented contract for that flag.
    """
    event = hookio.read_event()
    result = orchestrate.run(event)
    if result["outcome"] != "candidate":
        return 0
    hookio.wake(result["message"])
    return 2


def improve(argv):
    """Force a review of the current turn (spec section 3.2).

    The same bounded pipeline as the automatic path, not a second route to
    mutation. Used when automatic detection missed something worth keeping.
    """
    parser = argparse.ArgumentParser(prog="si improve")
    parser.add_argument("--focus", default="")
    parser.add_argument("--session-id")
    options = parser.parse_args(argv)

    event = hookio.read_event()
    if options.session_id:
        event.setdefault("session_id", options.session_id)

    result = orchestrate.run(event, forced=True, focus=options.focus or None)
    if result["outcome"] == "candidate":
        return _emit({"outcome": "candidate",
                      "candidate": result["candidate"]})
    return _emit(result)


def session_start(argv):
    """Surface candidates found while no session was available (section 11)."""
    event = hookio.read_event()
    waiting = orchestrate.pending_candidates(cwd=event.get("cwd"))
    if not waiting:
        return 0
    lines = ["self-improve: %d retained learning candidate%s from an earlier "
             "session." % (len(waiting), "" if len(waiting) == 1 else "s")]
    for entry in waiting[:5]:
        lines.append("  %s: %s" % (entry["candidate_id"], entry.get("lesson", "")))
    lines.append("Mention them only if the user asks; running the self-improve "
                 "improve skill with a candidate id will route and stage one.")
    hookio.additional_context("SessionStart", "\n".join(lines))
    return 0


def capture_expansion(argv):
    """Record authorization from a user-typed plugin command (section 5.2).

    The matcher in hooks.json is deliberately wide and the selection happens
    here, because the namespaced form Claude Code reports in ``command_name``
    for a plugin skill is not guaranteed across versions. A matcher that failed
    to match would silently discard the user's authorization; this fails loudly
    or not at all.
    """
    event = hookio.read_event()
    operation = authz.accepts(event)
    if operation is None:
        return 0

    try:
        arguments = authz.parse_arguments(operation, event.get("command_args"))
    except authz.AuthorizationError as exc:
        hookio.additional_context(
            "UserPromptExpansion",
            "self-improve: %s was not authorized: %s. Expected "
            "/self-improve:apply <proposal-id> <hash-prefix>, "
            "/self-improve:reject <proposal-id>, or "
            "/self-improve:rollback <mutation-id>." % (operation, exc.reason),
        )
        return 0

    authz.grant(event, operation, arguments)
    identifier = arguments.get("proposal_id") or arguments.get("mutation_id")
    hookio.additional_context(
        "UserPromptExpansion",
        "self-improve: the user authorized %s for %s by typing the command. "
        "Run `${CLAUDE_PLUGIN_ROOT}/scripts/si %s-%s %s` and report its result "
        "verbatim. Do not edit the target file yourself."
        % (operation, identifier, operation,
           "proposal" if operation != authz.ROLLBACK else "mutation",
           _argument_string(operation, arguments)),
    )
    return 0


def _argument_string(operation, arguments):
    if operation == authz.APPLY:
        return "--id %s --hash-prefix %s" % (arguments["proposal_id"],
                                             arguments["hash_prefix"])
    if operation == authz.REJECT:
        return "--id %s" % arguments["proposal_id"]
    return "--id %s" % arguments["mutation_id"]


def find_owners(argv):
    """List allowlisted artifacts that could own a lesson."""
    parser = argparse.ArgumentParser(prog="si find-owners")
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=25)
    options = parser.parse_args(argv)
    ranked = owners.search(options.query)[:options.limit]
    return _emit({"allowlist": allowlist.describe(), "owners": ranked})


def stage_proposal(argv):
    """Stage one immutable proposal and print it for presentation.

    The new content arrives on standard input rather than as an argument, so
    the bytes staged are exactly the bytes supplied, with no shell quoting in
    between.
    """
    parser = argparse.ArgumentParser(prog="si stage-proposal")
    parser.add_argument("--target", required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--reason", default="")
    parser.add_argument("--content-file")
    options = parser.parse_args(argv)

    if options.content_file:
        with open(options.content_file, "rb") as handle:
            data = handle.read()
    else:
        data = sys.stdin.buffer.read()

    candidate = {}
    if options.candidate:
        candidate = store.read_record(store.CANDIDATES, options.candidate) or {}
        candidate["candidate_id"] = options.candidate

    fingerprint = proposals.fingerprint(
        candidate.get("lesson", ""), *_scope_and_kind(options.target))
    status = journal.fingerprint_status(fingerprint)
    if status == "rejected":
        return _fail("duplicate_of_rejected_proposal")

    try:
        record = proposals.stage(options.target, data, candidate=candidate,
                                 reason=options.reason)
    except proposals.ProposalError as exc:
        return _fail(exc.reason, exc.detail)

    sys.stdout.write(proposals.summary(record) + "\n")
    return 0


def _scope_and_kind(target):
    try:
        resolved = allowlist.resolve(target)
    except allowlist.PathRejected:
        return ("", "")
    return (resolved["scope"], resolved["kind"])


def show_proposal(argv):
    parser = argparse.ArgumentParser(prog="si show-proposal")
    parser.add_argument("--id", required=True)
    options = parser.parse_args(argv)
    try:
        record = proposals.load(options.id)
    except proposals.ProposalError as exc:
        return _fail(exc.reason)
    sys.stdout.write(proposals.summary(record) + "\n")
    return 0


def apply_proposal(argv):
    """Install a staged proposal, consuming its one-time authorization."""
    parser = argparse.ArgumentParser(prog="si apply-proposal")
    parser.add_argument("--id", required=True)
    parser.add_argument("--hash-prefix", required=True)
    parser.add_argument("--session-id")
    options = parser.parse_args(argv)

    try:
        authz.consume(authz.APPLY, session_id=options.session_id,
                      proposal_id=options.id,
                      hash_prefix=options.hash_prefix.lower())
    except authz.AuthorizationError as exc:
        return _fail(
            exc.reason,
            "a proposal is applied only after the user types "
            "/self-improve:apply <id> <hash-prefix>")

    try:
        record = mutate.apply_proposal(options.id, options.hash_prefix)
    except (mutate.MutationError, proposals.ProposalError) as exc:
        return _fail(exc.reason, getattr(exc, "detail", None))

    sys.stdout.write(
        "Applied %s to %s.\nMutation %s. Roll back with "
        "/self-improve:rollback %s\n"
        % (options.id, record["target"], record["mutation_id"],
           record["mutation_id"]))
    return 0


def reject_proposal(argv):
    """Discard a proposal, keeping only its fingerprint and a reason category."""
    parser = argparse.ArgumentParser(prog="si reject-proposal")
    parser.add_argument("--id", required=True)
    parser.add_argument("--reason-category", default="declined")
    parser.add_argument("--session-id")
    options = parser.parse_args(argv)

    try:
        authz.consume(authz.REJECT, session_id=options.session_id,
                      proposal_id=options.id)
    except authz.AuthorizationError as exc:
        return _fail(exc.reason)

    try:
        record = proposals.load(options.id)
    except proposals.ProposalError as exc:
        return _fail(exc.reason)

    journal.record_fingerprint(record["fingerprint"], "rejected",
                               reason_category=options.reason_category)
    proposals.invalidate(options.id)
    sys.stdout.write("Rejected %s. %s is unchanged.\n"
                     % (options.id, record["target"]))
    return 0


def rollback_mutation(argv):
    """Restore a verified preimage."""
    parser = argparse.ArgumentParser(prog="si rollback-mutation")
    parser.add_argument("--id", required=True)
    parser.add_argument("--session-id")
    options = parser.parse_args(argv)

    try:
        authz.consume(authz.ROLLBACK, session_id=options.session_id,
                      mutation_id=options.id)
    except authz.AuthorizationError as exc:
        return _fail(exc.reason)

    try:
        record = mutate.rollback_mutation(options.id)
    except mutate.MutationError as exc:
        return _fail(exc.reason, exc.detail)

    sys.stdout.write("Rolled back %s. %s restored to its previous contents.\n"
                     % (options.id, record["target"]))
    return 0


def show_candidate(argv):
    parser = argparse.ArgumentParser(prog="si show-candidate")
    parser.add_argument("--id")
    options = parser.parse_args(argv)
    if options.id:
        record = store.read_record(store.CANDIDATES, options.id)
        if record is None:
            return _fail("unknown_or_expired_candidate")
        # Reading a candidate is the moment it stops awaiting presentation, so
        # the recursion guard lifts and the next turn can be reviewed again.
        gate.clear_awaiting_presentation(record.get("session_id"))
        orchestrate.drop_pending(options.id)
        return _emit(record)
    return _emit({"candidates": store.list_records(store.CANDIDATES)})


def session_end(argv):
    """Expire ephemeral state (spec section 5.6).

    Deliberately does no model work: the session is already terminating, and
    Claude Code gives ``SessionEnd`` hooks a shared budget of about 1.5 seconds.
    """
    hookio.read_event()
    store.sweep()
    return 0


def status(argv):
    """Report live state. Used by the skills and by the smoke test."""
    root = paths.state_root()
    report = {
        "state_root": root,
        "claude_home": paths.claude_home(),
        "plugin_root": paths.plugin_root(),
        "candidates": len(store.list_records(store.CANDIDATES)),
        "proposals": len(store.list_records(store.PROPOSALS)),
        "authorizations": len(store.list_records(store.AUTHORIZATIONS)),
        "disabled": config.disabled(),
        "review_model": config.review_model(),
    }
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def self_test(argv):
    """Verify install-time invariants and report what is wrong.

    Run from the smoke test and usable by hand. Unlike the hook paths this is
    allowed to fail loudly, because a person asked it a direct question.
    """
    failures = []

    # Reachable only when scripts/si.py is run directly, bypassing the shell
    # shim that guarantees a 3.9+ interpreter. Worth reporting rather than
    # failing with an obscure syntax or attribute error further along.
    if sys.version_info < (3, 9):  # noqa: UP036
        failures.append("interpreter is %s; 3.9 or later is required"
                        % platform.python_version())

    root = paths.state_root()
    try:
        paths.ensure_dir(root)
    except OSError as exc:
        failures.append("cannot create state root %s (%s)" % (root, exc.strerror))
    else:
        mode = os.stat(root).st_mode & 0o777
        if mode != paths.DIR_MODE:
            failures.append("state root %s has mode %o, expected %o"
                            % (root, mode, paths.DIR_MODE))
        probe = os.path.join(root, ".self-test")
        try:
            paths.atomic_write(probe, b"ok")
            if os.stat(probe).st_mode & 0o777 != paths.FILE_MODE:
                failures.append("state files are not created mode 600")
        except OSError as exc:
            failures.append("state root is not writable (%s)" % exc.strerror)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(probe)

    plugin = paths.plugin_root()
    for relative in ("hooks/hooks.json", ".claude-plugin/plugin.json", "scripts/si"):
        candidate = os.path.join(plugin, relative)
        if not os.path.exists(candidate):
            failures.append("missing plugin file %s" % relative)

    hooks_json = os.path.join(plugin, "hooks", "hooks.json")
    if os.path.exists(hooks_json):
        try:
            with open(hooks_json, encoding="utf-8") as handle:
                json.load(handle)
        except ValueError as exc:
            failures.append("hooks.json is not valid JSON (%s)" % exc)

    for line in failures:
        sys.stderr.write("self-test: %s\n" % line)
    for line in cli_capability_warnings():
        sys.stderr.write("self-test: warning: %s\n" % line)
    if failures:
        return 1
    sys.stdout.write("self-test: ok (python %s, state root %s)\n"
                     % (platform.python_version(), root))
    return 0


# The floor is set by the highest documented requirement among the hook fields
# this plugin reads: prompt_id on the common input fields, which the hooks
# reference states requires v2.1.196. background_tasks and session_crons on Stop
# require v2.1.145. UserPromptExpansion carries the authorization path of spec
# section 5.2 and is absent from v2.1.81; the reference states no introduction
# version for it, so it is covered by the same floor rather than guessed at.
MINIMUM_CLI_VERSION = (2, 1, 196)

CLI_FEATURES_AT_FLOOR = (
    "UserPromptExpansion (mutation authorization), prompt_id (turn identity), "
    "and background_tasks/session_crons on Stop (skipping review while "
    "background work is in flight)"
)


def _format_version(version):
    return ".".join(str(part) for part in version)


def cli_version():
    """The installed Claude Code version as a tuple, or ``None``.

    ``None`` when the CLI is absent or does not answer, which is normal in
    tests and during offline development.
    """
    executable = shutil.which("claude")
    if not executable:
        return None
    try:
        result = subprocess.run([executable, "--version"], capture_output=True,
                                text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout or "")
    return tuple(int(part) for part in match.groups()) if match else None


def cli_capability_warnings():
    """Report an installed CLI too old for the hook contract this plugin uses.

    A warning rather than a failure: capture and review still work, and the
    package may be validated on one machine and run on another. What stops
    working is authorization, so the message says so plainly.
    """
    version = cli_version()
    if version is None or version >= MINIMUM_CLI_VERSION:
        return []
    return [
        "Claude Code %s is older than %s. Without an upgrade, %s are "
        "unavailable, so proposals cannot be authorized or applied."
        % (_format_version(version), _format_version(MINIMUM_CLI_VERSION),
           CLI_FEATURES_AT_FLOOR)
    ]


HANDLERS = {
    "capture-prompt": capture_prompt,
    "capture-expansion": capture_expansion,
    "capture-tool-failure": capture_tool_failure,
    "capture-tool-success": capture_tool_success,
    "review-turn": review_turn,
    "improve": improve,
    "session-start": session_start,
    "session-end": session_end,
    "find-owners": find_owners,
    "show-candidate": show_candidate,
    "stage-proposal": stage_proposal,
    "show-proposal": show_proposal,
    "apply-proposal": apply_proposal,
    "reject-proposal": reject_proposal,
    "rollback-mutation": rollback_mutation,
    "status": status,
    "self-test": self_test,
}
